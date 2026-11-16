"""Detección por postura y movimiento, sin cámara, relojes propios ni alertas."""

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
    """Procesa una persona, con llamadas secuenciales y tiempos siempre crecientes.

    ON_FLOOR indica una postura compatible con estar en el suelo, no su ubicación.
    Solo acumula tiempo horizontal observado. Los intentos de recuperación y la
    falta de datos lo pausan; la recuperación estable confirmada cierra el episodio.
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
        timestamp = measurement.timestamp
        if not _finite(timestamp) or timestamp < 0:
            raise ValueError("timestamp debe ser un número finito no negativo, en segundos crecientes")
        if self._last_timestamp is not None and timestamp <= self._last_timestamp:
            raise ValueError("Cada timestamp debe ser mayor que el anterior")
        self._last_timestamp = timestamp
        events: list[DetectorEvent] = []
        since_valid = None if self._last_valid is None else timestamp - self._last_valid
        reason = self._invalid_reason(measurement)
        if (self._tracked and since_valid is not None
                and since_valid >= self.config.tracking_timeout_seconds):
            self._tracked = False
            self._emit(events, Event.PERSON_LOST, timestamp)
            self._break_continuity()
            if self._episode_id is None:
                self._state = State.NO_PERSON
        if reason is not None:
            self._break_continuity()
            tracking = Tracking.INVALID if measurement.person_present else Tracking.ABSENT
            if not self._tracked and self._last_valid is not None:
                tracking = Tracking.LOST
            return self._result(
                timestamp=timestamp, tracking=tracking, events=events, reason=reason,
            )
        if since_valid is not None and since_valid > self.config.max_sample_gap_seconds:
            self._break_continuity()
        if not self._tracked:
            self._tracked = True
            self._emit(events, Event.PERSON_DETECTED, timestamp)
        self._last_valid = timestamp

        lying = self._lying(measurement)
        if self._criterion == Criterion.RAPID_DESCENT:
            lying = lying or measurement.aspect_ratio >= self.config.lying_aspect_ratio
        speed, descent, baseline = self._observe(measurement)
        angle_change, body_descent, posture_candidate = self._posture_evidence(measurement, baseline)
        if self._episode_id is None:
            self._monitor(measurement, lying, speed, descent, baseline, posture_candidate, events)
        if self._state == State.FALLING:
            if timestamp - self._fall_started > self.config.fall_timeout_seconds:
                self._clear_episode()
                self._state = self._normal_state(measurement)
            elif lying or measurement.aspect_ratio >= self.config.lying_aspect_ratio:
                lying = True
                self._enter_floor(timestamp, events)
        if self._state in (State.ON_FLOOR, State.RECOVERING):
            self._advance_episode(measurement, lying, events)
        return self._result(
            timestamp=timestamp,
            tracking=Tracking.VALID,
            events=events,
            measurement=measurement,
            speed=speed,
            descent=descent,
            angle_change=angle_change,
            body_descent=body_descent,
        )

    def _lying(self, measurement: Measurement) -> bool:
        if measurement.torso_angle is None:
            return measurement.aspect_ratio >= self.config.lying_aspect_ratio
        # Una silueta ancha al sentarse no basta. El ángulo permite reconocer
        # cuerpos girados que se ven más cortos por la perspectiva.
        return (measurement.torso_angle >= self.config.lying_torso_angle
                and measurement.aspect_ratio >= self.config.upright_aspect_ratio)

    def _normal_state(self, measurement: Measurement) -> State:
        return (
            State.STANDING
            if measurement.aspect_ratio <= self.config.upright_aspect_ratio
            else State.UNKNOWN
        )

    def _observe(self, measurement: Measurement):
        timestamp = measurement.timestamp
        while (
            len(self._history) > 1
            and self._history[1].timestamp <= timestamp - self.config.posture_window_seconds
        ):
            self._history.popleft()
        motion_reference = None
        for previous in self._history:
            if previous.timestamp <= timestamp - self.config.speed_window_seconds:
                motion_reference = previous
        baseline = next((previous for previous in self._history if not self._lying(previous)), None)
        self._history.append(measurement)
        if motion_reference is None:
            return None, None, baseline
        descent = (measurement.hip_y - motion_reference.hip_y) / motion_reference.torso_length
        return descent / (timestamp - motion_reference.timestamp), descent, baseline

    def _posture_evidence(self, measurement: Measurement, baseline):
        if baseline is None:
            return None, None, False
        descent = (measurement.hip_y - baseline.hip_y) / baseline.torso_length
        if measurement.shoulder_y is not None and baseline.shoulder_y is not None:
            descent = max(
                descent,
                (measurement.shoulder_y - baseline.shoulder_y) / baseline.torso_length,
            )
        config = self.config
        if measurement.torso_angle is not None and baseline.torso_angle is not None:
            change = measurement.torso_angle - baseline.torso_angle
            changed = change >= config.posture_angle_change
            rotated = change >= config.posture_rotation_threshold
        else:
            change = None
            changed = measurement.aspect_ratio - baseline.aspect_ratio >= config.posture_aspect_change
            rotated = False
        return change, descent, changed and (descent >= config.posture_min_descent or rotated)

    def _monitor(self, measurement, lying, speed, descent, baseline, posture_candidate, events):
        timestamp = measurement.timestamp
        self._state = self._normal_state(measurement)
        if not lying:
            self._horizontal_since = None
            self._posture_since = None
        elif self._horizontal_since is None:
            self._horizontal_since = timestamp
        if not (lying and posture_candidate):
            self._posture_since = None
        elif self._posture_since is None:
            self._posture_since = timestamp
        config = self.config
        if (baseline is not None and speed is not None
                and speed >= config.fall_speed_threshold and descent >= config.min_descent):
            self._start_episode(Criterion.RAPID_DESCENT, baseline)
            self._state = State.FALLING
            self._fall_started = timestamp
            self._emit(events, Event.FALL_STARTED, timestamp)
        elif (
            self._posture_since is not None
            and timestamp - self._posture_since >= config.posture_hold_seconds
        ):
            self._start_episode(Criterion.POSTURE_CHANGE, baseline)
            self._emit(events, Event.FALL_SUSPECTED, timestamp)
            self._enter_floor(timestamp, events, timestamp - self._horizontal_since)
        elif (
            self._horizontal_since is not None
            and timestamp - self._horizontal_since >= config.floor_persistence_seconds
        ):
            self._start_episode(Criterion.PERSISTENT_POSTURE, baseline)
            self._emit(events, Event.FALL_SUSPECTED, timestamp)
            self._enter_floor(timestamp, events, timestamp - self._horizontal_since)

    def _start_episode(self, criterion, baseline):
        self._episode_id = str(uuid4())
        self._criterion = criterion
        self._reference = baseline

    def _enter_floor(self, timestamp, events, observed_seconds=0.0):
        self._state = State.ON_FLOOR
        self._floor_seconds += observed_seconds
        self._floor_previous = timestamp
        if not self._on_floor_emitted:
            self._emit(events, Event.PERSON_ON_FLOOR, timestamp)
            self._on_floor_emitted = True

    def _recovered_pose(self, measurement):
        config = self.config
        vertical = (
            measurement.torso_angle <= config.upright_torso_angle
            if measurement.torso_angle is not None
            else measurement.aspect_ratio <= config.upright_aspect_ratio
        )
        if not vertical:
            return False
        if self._reference is None:
            return True
        return ((measurement.hip_y - self._reference.hip_y) / self._reference.torso_length
                <= config.recovery_hip_tolerance)

    def _advance_episode(self, measurement, lying, events):
        timestamp = measurement.timestamp
        if lying:
            self._state = State.ON_FLOOR
            self._recovery_since = None
            if self._floor_previous is not None:
                self._floor_seconds += timestamp - self._floor_previous
            self._floor_previous = timestamp
            if not self._confirmed and self._floor_seconds >= self.config.floor_confirm_seconds:
                self._emit(events, Event.FALL_CONFIRMED, timestamp)
                self._confirmed = True
        else:
            self._state = State.RECOVERING
            self._floor_previous = None
            if not self._recovered_pose(measurement):
                self._recovery_since = None
            elif self._recovery_since is None:
                self._recovery_since = timestamp
            elif timestamp - self._recovery_since >= self.config.recovery_seconds:
                self._emit(events, Event.PERSON_RECOVERED, timestamp)
                self._clear_episode()
                self._state = State.RECOVERED

    def _invalid_reason(self, measurement: Measurement) -> Optional[str]:
        if not isinstance(measurement.person_present, bool):
            return "person_present debe ser un booleano"
        if not measurement.person_present:
            return "person_absent"
        if not _finite(measurement.visibility) or not 0 <= measurement.visibility <= 1:
            return "visibility debe ser un número finito entre 0 y 1"
        if measurement.visibility < self.config.min_visibility:
            return "low_visibility"
        if not _finite(measurement.hip_y):
            return "hip_y debe ser un número finito"
        if not _finite(measurement.torso_length) or measurement.torso_length <= 0:
            return "torso_length debe ser un número finito y positivo"
        if not _finite(measurement.aspect_ratio) or measurement.aspect_ratio <= 0:
            return "aspect_ratio debe ser un número finito y positivo"
        if measurement.shoulder_y is not None and not _finite(measurement.shoulder_y):
            return "shoulder_y debe ser un número finito cuando se incluye"
        if measurement.torso_angle is not None and (
            not _finite(measurement.torso_angle) or not 0 <= measurement.torso_angle <= 90
        ):
            return "torso_angle debe ser un número finito entre 0 y 90 grados"
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

    def _emit(self, events, kind, timestamp):
        events.append(DetectorEvent(
            event_id=str(uuid4()),
            type=kind,
            timestamp=timestamp,
            episode_id=self._episode_id,
            floor_seconds=self._floor_seconds,
            criterion=self._criterion,
        ))

    def _result(self, timestamp, tracking, events, measurement=None, speed=None, descent=None,
                angle_change=None, body_descent=None, reason=None):
        return DetectorResult(
            timestamp=timestamp, state=self._state if self._tracked else State.NO_PERSON,
            tracking=tracking, events=tuple(events), episode_id=self._episode_id,
            criterion=self._criterion,
            metrics=DebugMetrics(
                fall_speed=speed, hip_descent=descent,
                aspect_ratio=measurement.aspect_ratio if measurement is not None else None,
                floor_seconds=self._floor_seconds,
                recovery_seconds=0.0 if self._recovery_since is None else timestamp - self._recovery_since,
                seconds_since_valid=None if self._last_valid is None else timestamp - self._last_valid,
                invalid_reason=reason,
                torso_angle=measurement.torso_angle if measurement is not None else None,
                posture_change=angle_change, body_descent=body_descent,
                candidate_seconds=(0.0 if self._horizontal_since is None or self._episode_id is not None
                                   else timestamp - self._horizontal_since),
            ),
        )
