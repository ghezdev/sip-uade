"""Cuenta regresiva a partir de eventos. READY no implica que se envió un mensaje."""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Optional, Sequence

from fall_detection.models import DetectorEvent, DetectorState, EventType, TrackingStatus


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
    paused: bool = False
    paused_seconds: float = 0.0
    pause_exhausted: bool = False


class AlertWorkflow:
    """Procesa los eventos de un detector usando su misma línea de tiempo.

    Los intentos de recuperación comparten un presupuesto limitado de pausa.
    La recuperación confirmada tiene prioridad si coincide con el vencimiento.
    """

    def __init__(self, cancel_seconds: float = 30.0, *, max_sample_gap_seconds: float = 0.5):
        if (isinstance(cancel_seconds, bool) or not isinstance(cancel_seconds, (float, int))
                or not isfinite(cancel_seconds) or cancel_seconds <= 0):
            raise ValueError("cancel_seconds debe ser un número finito y positivo")
        if (isinstance(max_sample_gap_seconds, bool)
                or not isinstance(max_sample_gap_seconds, (float, int))
                or not isfinite(max_sample_gap_seconds) or max_sample_gap_seconds <= 0):
            raise ValueError("max_sample_gap_seconds debe ser un número finito y positivo")
        self.cancel_seconds = cancel_seconds
        self.max_sample_gap_seconds = max_sample_gap_seconds
        self._state = AlertState.IDLE
        self._episode_id = None
        self._deadline = None
        self._last_timestamp = None
        self._handled = set()
        self._closed = set()
        self._dispatched = set()
        self._paused_seconds = 0.0
        self._previous_recovering = False

    def mark_dispatched(self, episode_id: str) -> None:
        """Una alerta entregada al servicio externo ya no se cancela localmente."""
        if episode_id != self._episode_id or self._state != AlertState.READY:
            raise ValueError("Solo se puede despachar una alerta cuya cuenta haya vencido")
        self._dispatched.add(episode_id)

    def update(self, events: Sequence[DetectorEvent], timestamp: float, *,
               detector_state=None, tracking=None, episode_id=None) -> AlertSnapshot:
        if (isinstance(timestamp, bool) or not isinstance(timestamp, (float, int))
                or not isfinite(timestamp) or timestamp < 0
                or (self._last_timestamp is not None and timestamp < self._last_timestamp)):
            raise ValueError("El tiempo de alerta debe ser finito, no negativo y no puede retroceder")
        if any(not isfinite(e.timestamp) or e.timestamp > timestamp for e in events):
            raise ValueError("El tiempo de cada evento debe ser finito y no puede superar el tiempo de actualización")
        elapsed = None if self._last_timestamp is None else timestamp - self._last_timestamp
        # La recuperación confirmada tiene prioridad, incluso justo al vencer la cuenta.
        for event in events:
            if event.type == EventType.PERSON_RECOVERED and event.episode_id:
                self._closed.add(event.episode_id)
                if (event.episode_id == self._episode_id
                        and event.episode_id not in self._dispatched):
                    self._state = AlertState.CANCELLED
        for event in events:
            episode = event.episode_id
            if (event.type == EventType.FALL_CONFIRMED and episode
                    and episode not in self._handled and episode not in self._closed):
                self._handled.add(episode)
                self._episode_id = episode
                self._deadline = event.timestamp + self.cancel_seconds
                self._state = AlertState.COUNTDOWN
                self._paused_seconds = 0.0
                self._previous_recovering = False
        valid_episode = tracking == TrackingStatus.VALID and episode_id == self._episode_id
        tracking_lost = any(event.type == EventType.PERSON_LOST for event in events)
        if (self._state == AlertState.COUNTDOWN and self._previous_recovering
                and valid_episode and not tracking_lost and elapsed is not None
                and elapsed <= self.max_sample_gap_seconds):
            # El intervalo anterior solo se pausa si sigue habiendo datos válidos y continuos.
            pause_seconds = min(elapsed, self.cancel_seconds - self._paused_seconds)
            self._paused_seconds += pause_seconds
            self._deadline += pause_seconds
        if self._state == AlertState.COUNTDOWN and timestamp >= self._deadline:
            self._state = AlertState.READY
        pause_exhausted = self._paused_seconds >= self.cancel_seconds
        recovering = valid_episode and detector_state == DetectorState.RECOVERING
        paused = self._state == AlertState.COUNTDOWN and recovering and not pause_exhausted
        self._previous_recovering = paused
        self._last_timestamp = timestamp
        remaining = (max(0.0, self._deadline - timestamp)
                     if self._state == AlertState.COUNTDOWN else None)
        return AlertSnapshot(
            state=self._state, episode_id=self._episode_id, deadline=self._deadline,
            remaining_seconds=remaining, paused=paused, paused_seconds=self._paused_seconds,
            pause_exhausted=pause_exhausted,
        )
