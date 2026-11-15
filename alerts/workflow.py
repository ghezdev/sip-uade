"""Event-driven cancellation window. READY is local, not a sent notification."""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Optional, Sequence

from fall_detection.models import DetectorEvent, EventType


class AlertState(str, Enum):
    IDLE = "IDLE"
    COUNTDOWN = "COUNTDOWN"
    CANCELLED = "CANCELLED"
    READY = "READY"


@dataclass(frozen=True)
class AlertSnapshot:
    state: AlertState
    episode_id: Optional[str] = None
    deadline: Optional[float] = None
    remaining_seconds: Optional[float] = None


class AlertWorkflow:
    """One stream. Provisional recovery/loss cannot cancel or restart a countdown.

    Caller supplies the same timeline as detector events. Stable recovery wins
    when it arrives exactly at the deadline. No HTTP, sending or sleeping occurs.
    """

    def __init__(self, cancel_seconds: float = 30.0):
        if (isinstance(cancel_seconds, bool) or not isinstance(cancel_seconds, (float, int))
                or not isfinite(cancel_seconds) or cancel_seconds <= 0):
            raise ValueError("cancel_seconds must be finite and positive")
        self.cancel_seconds = cancel_seconds
        self._state = AlertState.IDLE
        self._episode_id = None
        self._deadline = None
        self._last_timestamp = None
        self._handled = set()
        self._closed = set()

    def update(self, events: Sequence[DetectorEvent], timestamp: float) -> AlertSnapshot:
        if (isinstance(timestamp, bool) or not isinstance(timestamp, (float, int))
                or not isfinite(timestamp) or timestamp < 0
                or (self._last_timestamp is not None and timestamp < self._last_timestamp)):
            raise ValueError("alert timestamps must be finite and nondecreasing")
        if any(not isfinite(e.timestamp) or e.timestamp > timestamp for e in events):
            raise ValueError("event timestamps must not be in the future")
        self._last_timestamp = timestamp
        # Process confirmed recovery before confirmations/deadline evaluation.
        for event in events:
            if event.type == EventType.PERSON_RECOVERED and event.episode_id:
                self._closed.add(event.episode_id)
                if event.episode_id == self._episode_id:
                    self._state = AlertState.CANCELLED
        for event in events:
            episode = event.episode_id
            if (event.type == EventType.FALL_CONFIRMED and episode
                    and episode not in self._handled and episode not in self._closed):
                self._handled.add(episode)
                self._episode_id = episode
                self._deadline = event.timestamp + self.cancel_seconds
                self._state = AlertState.COUNTDOWN
        if self._state == AlertState.COUNTDOWN and timestamp >= self._deadline:
            self._state = AlertState.READY
        remaining = (max(0.0, self._deadline - timestamp)
                     if self._state == AlertState.COUNTDOWN else None)
        return AlertSnapshot(self._state, self._episode_id, self._deadline, remaining)
