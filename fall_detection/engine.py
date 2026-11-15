"""Geometry and temporal evidence, independent of frames, clocks and alerts."""

from collections import deque
from math import isfinite
from typing import Optional
from uuid import uuid4

from .config import DetectorConfig
from .models import (
    DebugMetrics, DetectionCriterion as Criterion, DetectorEvent, DetectorResult,
    DetectorState as State, EventType as Event, Measurement, TrackingStatus as Tracking,
)


def _finite(value: object) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and isfinite(value))


class FallDetector:
    """Single-owner, single-person stream using caller-supplied monotonic seconds.

    ON_FLOOR means a compatible posture, never confirmed scene location.
    Floor time accumulates observed horizontal intervals only. Recovery and gaps
    pause it; only confirmed stable recovery closes an established floor episode.
    """

    def __init__(self, config: Optional[DetectorConfig] = None) -> None:
        self.config = config or DetectorConfig()
        self._state = State.NO_PERSON
        self._last_timestamp = None
        self._last_valid = None
        self._tracked = False
        self._history: deque[Measurement] = deque()
        self._episode_id = None
        self._criterion = None
        self._reference = None
        self._fall_started = None
        self._confirmed = False
        self._on_floor_emitted = False
        self._floor_seconds = 0.0
        self._floor_previous = None
        self._recovery_since = None
        self._horizontal_since = None
        self._posture_since = None

    def update(self, measurement: Measurement) -> DetectorResult:
        t = measurement.timestamp
        if not _finite(t) or t < 0:
            raise ValueError("timestamp must be finite, nonnegative monotonic seconds")
        if self._last_timestamp is not None and t <= self._last_timestamp:
            raise ValueError("timestamps must be strictly increasing")
        self._last_timestamp = t
        events: list[DetectorEvent] = []
        since_valid = None if self._last_valid is None else t - self._last_valid
        reason = self._invalid_reason(measurement)
        if (self._tracked and since_valid is not None
                and since_valid >= self.config.tracking_timeout_seconds):
            self._tracked = False
            self._emit(events, Event.PERSON_LOST, t)
            self._break_continuity()
            if self._episode_id is None:
                self._state = State.NO_PERSON
        if reason is not None:
            self._break_continuity()
            tracking = Tracking.INVALID if measurement.person_present else Tracking.ABSENT
            if not self._tracked and self._last_valid is not None:
                tracking = Tracking.LOST
            return self._result(t, tracking, events, reason=reason)
        if since_valid is not None and since_valid > self.config.max_sample_gap_seconds:
            self._break_continuity()
        if not self._tracked:
            self._tracked = True
            self._emit(events, Event.PERSON_DETECTED, t)
        self._last_valid = t

        lying = self._lying(measurement)
        if self._criterion == Criterion.RAPID_DESCENT:
            lying = lying or measurement.aspect_ratio >= self.config.lying_aspect_ratio
        speed, descent, baseline = self._observe(measurement)
        angle_change, body_descent, posture_candidate = self._posture_evidence(measurement, baseline)
        if self._episode_id is None:
            self._monitor(measurement, lying, speed, descent, baseline, posture_candidate, events)
        if self._state == State.FALLING:
            if t - self._fall_started > self.config.fall_timeout_seconds:
                self._clear_episode()
                self._state = self._normal_state(measurement)
            elif lying or measurement.aspect_ratio >= self.config.lying_aspect_ratio:
                lying = True
                self._enter_floor(t, events)
        if self._state in (State.ON_FLOOR, State.RECOVERING):
            self._advance_episode(measurement, lying, events)
        return self._result(t, Tracking.VALID, events, measurement, speed, descent,
                            angle_change, body_descent)

    def _lying(self, m: Measurement) -> bool:
        if m.torso_angle is None:
            return m.aspect_ratio >= self.config.lying_aspect_ratio
        # A wide seated silhouette alone is insufficient. Angle also allows
        # rotated, partly foreshortened bodies below the old aspect threshold.
        return (m.torso_angle >= self.config.lying_torso_angle
                and m.aspect_ratio >= self.config.upright_aspect_ratio)

    def _normal_state(self, m: Measurement) -> State:
        return State.STANDING if m.aspect_ratio <= self.config.upright_aspect_ratio else State.UNKNOWN

    def _observe(self, m: Measurement):
        t = m.timestamp
        while len(self._history) > 1 and self._history[1].timestamp <= t - self.config.posture_window_seconds:
            self._history.popleft()
        motion_ref = None
        for previous in self._history:
            if previous.timestamp <= t - self.config.speed_window_seconds:
                motion_ref = previous
        baseline = next((p for p in self._history if not self._lying(p)), None)
        self._history.append(m)
        if motion_ref is None:
            return None, None, baseline
        descent = (m.hip_y - motion_ref.hip_y) / motion_ref.torso_length
        return descent / (t - motion_ref.timestamp), descent, baseline

    def _posture_evidence(self, m: Measurement, baseline):
        if baseline is None:
            return None, None, False
        descent = (m.hip_y - baseline.hip_y) / baseline.torso_length
        if m.shoulder_y is not None and baseline.shoulder_y is not None:
            descent = max(descent, (m.shoulder_y - baseline.shoulder_y) / baseline.torso_length)
        c = self.config
        if m.torso_angle is not None and baseline.torso_angle is not None:
            change = m.torso_angle - baseline.torso_angle
            changed = change >= c.posture_angle_change
            rotated = change >= c.posture_rotation_threshold
        else:
            change = None
            changed = m.aspect_ratio - baseline.aspect_ratio >= c.posture_aspect_change
            rotated = False
        return change, descent, changed and (descent >= c.posture_min_descent or rotated)

    def _monitor(self, m, lying, speed, descent, baseline, posture_candidate, events):
        t = m.timestamp
        self._state = self._normal_state(m)
        if not lying:
            self._horizontal_since = None
            self._posture_since = None
        elif self._horizontal_since is None:
            self._horizontal_since = t
        if not (lying and posture_candidate):
            self._posture_since = None
        elif self._posture_since is None:
            self._posture_since = t
        c = self.config
        if (baseline is not None and speed is not None
                and speed >= c.fall_speed_threshold and descent >= c.min_descent):
            self._start_episode(Criterion.RAPID_DESCENT, baseline)
            self._state = State.FALLING
            self._fall_started = t
            self._emit(events, Event.FALL_STARTED, t)
        elif self._posture_since is not None and t - self._posture_since >= c.posture_hold_seconds:
            self._start_episode(Criterion.POSTURE_CHANGE, baseline)
            self._emit(events, Event.FALL_SUSPECTED, t)
            self._enter_floor(t, events, t - self._horizontal_since)
        elif self._horizontal_since is not None and t - self._horizontal_since >= c.floor_persistence_seconds:
            self._start_episode(Criterion.PERSISTENT_POSTURE, baseline)
            self._emit(events, Event.FALL_SUSPECTED, t)
            self._enter_floor(t, events, t - self._horizontal_since)

    def _start_episode(self, criterion, baseline):
        self._episode_id = str(uuid4())
        self._criterion = criterion
        self._reference = baseline

    def _enter_floor(self, t, events, observed_seconds=0.0):
        self._state = State.ON_FLOOR
        self._floor_seconds += observed_seconds
        self._floor_previous = t
        if not self._on_floor_emitted:
            self._emit(events, Event.PERSON_ON_FLOOR, t)
            self._on_floor_emitted = True

    def _recovered_pose(self, m):
        c = self.config
        vertical = (m.torso_angle <= c.upright_torso_angle if m.torso_angle is not None
                    else m.aspect_ratio <= c.upright_aspect_ratio)
        if not vertical:
            return False
        if self._reference is None:
            return True
        return ((m.hip_y - self._reference.hip_y) / self._reference.torso_length
                <= c.recovery_hip_tolerance)

    def _advance_episode(self, m, lying, events):
        t = m.timestamp
        if lying:
            self._state = State.ON_FLOOR
            self._recovery_since = None
            if self._floor_previous is not None:
                self._floor_seconds += t - self._floor_previous
            self._floor_previous = t
            if not self._confirmed and self._floor_seconds >= self.config.floor_confirm_seconds:
                self._emit(events, Event.FALL_CONFIRMED, t)
                self._confirmed = True
        else:
            self._state = State.RECOVERING
            self._floor_previous = None
            if not self._recovered_pose(m):
                self._recovery_since = None
            elif self._recovery_since is None:
                self._recovery_since = t
            elif t - self._recovery_since >= self.config.recovery_seconds:
                self._emit(events, Event.PERSON_RECOVERED, t)
                self._clear_episode()
                self._state = State.RECOVERED

    def _invalid_reason(self, m: Measurement) -> Optional[str]:
        if not isinstance(m.person_present, bool):
            return "person_present must be a bool"
        if not m.person_present:
            return "person_absent"
        if not _finite(m.visibility) or not 0 <= m.visibility <= 1:
            return "visibility must be finite and between 0 and 1"
        if m.visibility < self.config.min_visibility:
            return "low_visibility"
        if not _finite(m.hip_y):
            return "hip_y must be finite"
        if not _finite(m.torso_length) or m.torso_length <= 0:
            return "torso_length must be finite and positive"
        if not _finite(m.aspect_ratio) or m.aspect_ratio <= 0:
            return "aspect_ratio must be finite and positive"
        if m.shoulder_y is not None and not _finite(m.shoulder_y):
            return "shoulder_y must be finite when supplied"
        if m.torso_angle is not None and (not _finite(m.torso_angle) or not 0 <= m.torso_angle <= 90):
            return "torso_angle must be between 0 and 90 degrees"
        return None

    def _break_continuity(self):
        self._history.clear()
        self._horizontal_since = None
        self._posture_since = None
        self._floor_previous = None
        self._recovery_since = None

    def _clear_episode(self):
        self._episode_id = None
        self._criterion = None
        self._reference = None
        self._fall_started = None
        self._confirmed = False
        self._on_floor_emitted = False
        self._floor_seconds = 0.0
        self._floor_previous = None
        self._recovery_since = None
        self._horizontal_since = None
        self._posture_since = None

    def _emit(self, events, kind, t):
        events.append(DetectorEvent(str(uuid4()), kind, t, self._episode_id,
                                    self._floor_seconds, self._criterion))

    def _result(self, t, tracking, events, m=None, speed=None, descent=None,
                angle_change=None, body_descent=None, reason=None):
        return DetectorResult(
            timestamp=t, state=self._state if self._tracked else State.NO_PERSON,
            tracking=tracking, events=tuple(events), episode_id=self._episode_id,
            criterion=self._criterion,
            metrics=DebugMetrics(
                fall_speed=speed, hip_descent=descent,
                aspect_ratio=m.aspect_ratio if m is not None else None,
                floor_seconds=self._floor_seconds,
                recovery_seconds=0.0 if self._recovery_since is None else t - self._recovery_since,
                seconds_since_valid=None if self._last_valid is None else t - self._last_valid,
                invalid_reason=reason,
                torso_angle=m.torso_angle if m is not None else None,
                posture_change=angle_change, body_descent=body_descent,
                candidate_seconds=(0.0 if self._horizontal_since is None or self._episode_id is not None
                                   else t - self._horizontal_since),
            ),
        )
