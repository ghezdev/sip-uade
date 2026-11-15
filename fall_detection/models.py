"""Immutable input and output contracts; no camera or alert dependencies."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DetectorState(str, Enum):
    NO_PERSON = "NO_PERSON"
    UNKNOWN = "UNKNOWN"
    STANDING = "STANDING"
    FALLING = "FALLING"
    ON_FLOOR = "ON_FLOOR"
    RECOVERING = "RECOVERING"
    RECOVERED = "RECOVERED"


class TrackingStatus(str, Enum):
    VALID = "VALID"
    ABSENT = "ABSENT"
    INVALID = "INVALID"
    LOST = "LOST"


class EventType(str, Enum):
    PERSON_DETECTED = "person_detected"
    PERSON_LOST = "person_lost"
    FALL_STARTED = "fall_started"
    FALL_SUSPECTED = "fall_suspected"
    PERSON_ON_FLOOR = "person_on_floor"
    FALL_CONFIRMED = "fall_confirmed"
    PERSON_RECOVERED = "person_recovered"


class DetectionCriterion(str, Enum):
    RAPID_DESCENT = "rapid_descent"
    POSTURE_CHANGE = "posture_change"
    PERSISTENT_POSTURE = "persistent_posture"


@dataclass(frozen=True)
class Measurement:
    """Seconds on one monotonic timeline; y grows downward.

    hip_y and torso_length must use the same spatial scale. aspect_ratio
    must be computed in an isotropic coordinate system by the future adapter.
    Missing body values are allowed, so invalid inputs reach the engine.
    """

    timestamp: float
    person_present: bool
    hip_y: Optional[float] = None
    torso_length: Optional[float] = None
    aspect_ratio: Optional[float] = None
    visibility: Optional[float] = None
    shoulder_y: Optional[float] = None
    torso_angle: Optional[float] = None  # degrees from image vertical, 0..90


@dataclass(frozen=True)
class DetectorEvent:
    event_id: str
    type: EventType
    timestamp: float
    episode_id: Optional[str] = None
    floor_seconds: float = 0.0
    criterion: Optional[DetectionCriterion] = None


@dataclass(frozen=True)
class DebugMetrics:
    fall_speed: Optional[float] = None
    hip_descent: Optional[float] = None
    aspect_ratio: Optional[float] = None
    floor_seconds: float = 0.0
    recovery_seconds: float = 0.0
    seconds_since_valid: Optional[float] = None
    invalid_reason: Optional[str] = None
    torso_angle: Optional[float] = None
    posture_change: Optional[float] = None
    body_descent: Optional[float] = None
    candidate_seconds: float = 0.0


@dataclass(frozen=True)
class DetectorResult:
    timestamp: float
    state: DetectorState
    tracking: TrackingStatus
    events: tuple[DetectorEvent, ...]
    metrics: DebugMetrics
    episode_id: Optional[str] = None
    criterion: Optional[DetectionCriterion] = None
