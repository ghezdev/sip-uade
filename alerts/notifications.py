"""Notificaciones por episodio con un único hilo para las solicitudes de red."""

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
import logging
from queue import Empty, Queue
from threading import Event, Thread
import time
from uuid import UUID, uuid4

from fall_detection.models import EventType
from .telegram import TelegramError, send_message
from .workflow import AlertState


LOG = logging.getLogger("carewatch.notifications")
ALERT_MESSAGE = (
    "CareWatch detectó una posible caída o permanencia prolongada en el suelo. "
    "La persona podría necesitar asistencia. Comunicate con ella para verificar cómo se encuentra."
)
RECOVERY_MESSAGE = (
    "CareWatch detectó una postura de recuperación después de la alerta. "
    "Contactá a la persona para verificar que se encuentra bien."
)


@dataclass(frozen=True)
class Recipient:
    contact_id: UUID | None
    chat_id: str


@dataclass
class RecipientSelection:
    ready: Event = field(default_factory=Event)
    recipient: Recipient | None = None
    reason: str = "Consultando destinatario en PostgreSQL"

    def complete(self, recipient, reason):
        if not self.ready.is_set():
            self.recipient = recipient
            self.reason = reason
            self.ready.set()


@dataclass
class Delivery:
    episode_id: str
    kind: str
    text: str
    state: str = "SENDING"
    attempts: int = 0
    retry_at: float = 0.0
    error: str = ""
    id: UUID = field(default_factory=uuid4)
    recipient: Recipient | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_attempt_at: datetime | None = None
    accepted_at: datetime | None = None
    next_retry_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class NotificationService:
    def __init__(self, enabled: bool, *, sender=send_message, clock=time.monotonic,
                 recipient_selection=None, history=None):
        self.enabled = enabled
        self.deliveries: dict[tuple[str, str], Delivery] = {}
        self._recovered = set()
        self._details = {}
        self._sender = sender
        self._clock = clock
        self._selection = recipient_selection
        self._history = history
        self._pending_alert = None
        self._tasks = Queue()
        self._results = Queue()
        self._result_ready = Event()
        self._stop = Event()
        self._closed = False
        self._drained = True
        self._thread = None
        if enabled:
            self._thread = Thread(target=self._work, name="carewatch-telegram", daemon=True)
            self._thread.start()

    def _work(self):
        while not self._stop.is_set():
            task = self._tasks.get()
            if task is None or self._stop.is_set():
                return
            episode_id, kind, text, recipient = task
            error = None
            self._results.put((episode_id, kind, "started", datetime.now(timezone.utc), None))
            self._result_ready.set()
            try:
                if recipient is None:
                    self._sender(text)
                else:
                    self._sender(text, chat_id=recipient.chat_id)
            except TelegramError as exc:
                error = exc
            except Exception:
                # No mostramos excepciones externas que puedan incluir el token en una URL.
                error = TelegramError("Error inesperado; no se pudo confirmar el envío.", uncertain=True)
            self._results.put((episode_id, kind, "finished", datetime.now(timezone.utc), error))
            self._result_ready.set()

    def _start(self, delivery):
        delivery.state = "SENDING"
        delivery.next_retry_at = None
        self._publish(delivery)
        self._tasks.put((delivery.episode_id, delivery.kind, delivery.text, delivery.recipient))
        LOG.info("episodio=%s mensaje=%s envio en cola", delivery.episode_id, delivery.kind)

    def _publish(self, delivery):
        delivery.updated_at = datetime.now(timezone.utc)
        if self._history is not None:
            try:
                self._history(replace(delivery))
            except Exception:
                LOG.error("No se pudo registrar el resultado del envío; no se repetirá el mensaje por este error")

    def _send_recovery(self, episode_id):
        initial = self.deliveries.get((episode_id, "alert"))
        key = (episode_id, "recovery")
        if (episode_id in self._recovered and initial is not None and initial.state == "SENT"
                and key not in self.deliveries):
            delivery = Delivery(episode_id, "recovery", RECOVERY_MESSAGE + f"\nEpisodio: {episode_id}")
            delivery.recipient = initial.recipient
            self.deliveries[key] = delivery
            self._start(delivery)

    def update(self, alert, events=()) -> bool:
        """Devuelve True solo cuando se despacha una nueva alerta inicial."""
        if self._closed or not self.enabled:
            return False
        for event in events:
            if event.type == EventType.FALL_CONFIRMED and event.episode_id not in self._details:
                detected_at = datetime.now().astimezone().isoformat(timespec="seconds")
                self._details[event.episode_id] = (
                    f"\nDetectado: {detected_at}"
                    f"\nPermanencia observada: {event.floor_seconds:.1f} s."
                )
            if event.type == EventType.PERSON_RECOVERED and event.episode_id:
                self._recovered.add(event.episode_id)
                self._send_recovery(event.episode_id)
        self.poll()
        if self._selection is not None:
            if not self._selection.ready.is_set():
                self._pending_alert = alert
                return False
            self._pending_alert = None
            if self._selection.recipient is None:
                self.enabled = False
                return False
        key = (alert.episode_id, "alert")
        if (alert.state == AlertState.READY and alert.episode_id
                and alert.episode_id not in self._recovered and key not in self.deliveries):
            text = (ALERT_MESSAGE + self._details.get(alert.episode_id, "")
                    + f"\nEpisodio: {alert.episode_id}")
            delivery = Delivery(alert.episode_id, "alert", text)
            if self._selection is not None:
                delivery.recipient = self._selection.recipient
            self.deliveries[key] = delivery
            self._start(delivery)
            return True
        return False

    def poll(self):
        """Solo el hilo principal modifica el registro de envíos."""
        if self._closed:
            return
        self._result_ready.clear()
        while True:
            try:
                episode_id, kind, phase, occurred_at, error = self._results.get_nowait()
            except Empty:
                break
            delivery = self.deliveries[(episode_id, kind)]
            if phase == "started":
                delivery.attempts += 1
                delivery.last_attempt_at = occurred_at
                self._publish(delivery)
                continue
            if error is None:
                delivery.state = "SENT"
                delivery.error = ""
                delivery.accepted_at = occurred_at
                delivery.next_retry_at = None
                self._publish(delivery)
                LOG.info("episodio=%s mensaje=%s envio confirmado por Telegram", episode_id, kind)
                self._send_recovery(episode_id)
            else:
                delivery.error = str(error)
                if error.uncertain:
                    delivery.state = "UNKNOWN"
                elif error.retry_after is not None and delivery.attempts < 3:
                    delivery.state = "RETRY"
                    delivery.retry_at = self._clock() + error.retry_after
                    delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=error.retry_after)
                else:
                    delivery.state = "FAILED"
                self._publish(delivery)
                LOG.error("episodio=%s mensaje=%s estado=%s: %s",
                          episode_id, kind, delivery.state, delivery.error)
        for delivery in list(self.deliveries.values()):
            if delivery.state == "RETRY" and self._clock() >= delivery.retry_at:
                self._start(delivery)

    def status(self, alert) -> str:
        if self.enabled and self._selection is not None and not self._selection.ready.is_set():
            return "Consultando destinatario de Telegram"
        if not self.enabled:
            if alert.paused:
                return "Alerta pausada por recuperacion | Notificaciones externas deshabilitadas"
            return "Notificaciones externas deshabilitadas"
        initial = self.deliveries.get((alert.episode_id, "alert"))
        if initial is None:
            if alert.state == AlertState.COUNTDOWN:
                if alert.paused:
                    return "Alerta pausada por recuperacion"
                if alert.pause_exhausted:
                    return "Alerta pendiente: limite de pausa alcanzado"
                return "Alerta pendiente"
            if alert.state == AlertState.CANCELLED:
                return "Alerta cancelada por recuperacion"
            return "Sin alertas pendientes" if alert.state == AlertState.IDLE else "Alerta pendiente"
        labels = {
            "SENDING": "Envio en curso", "SENT": "Alerta enviada",
            "RETRY": "Error de envio: reintento pendiente", "FAILED": "Error de envio",
            "UNKNOWN": "Envio no confirmado: revisar el chat",
        }
        text = labels[initial.state]
        if alert.episode_id in self._recovered:
            recovery = self.deliveries.get((alert.episode_id, "recovery"))
            if recovery is None:
                text += " | Recuperacion registrada; alerta sin confirmacion"
            elif recovery.state == "SENT":
                text += " | Recuperacion posterior notificada"
            else:
                text += " | Recuperacion posterior: " + labels[recovery.state].lower()
        return text

    def close(self, timeout=3.0) -> bool:
        """Intenta terminar lo pendiente sin esperar indefinidamente a la red."""
        if self._closed:
            return self._drained
        deadline = time.monotonic() + timeout
        if (self.enabled and self._selection is not None and self._pending_alert is not None
                and self._pending_alert.state == AlertState.READY):
            while not self._selection.ready.is_set() and time.monotonic() < deadline:
                self._selection.ready.wait(min(.05, max(0.0, deadline - time.monotonic())))
            if self._selection.ready.is_set():
                self.update(self._pending_alert)
        unresolved = (self._pending_alert is not None and self._pending_alert.state == AlertState.READY
                      and self._pending_alert.episode_id not in self._recovered)
        while True:
            self.poll()
            pending = [d for d in self.deliveries.values() if d.state in ("SENDING", "RETRY")]
            remaining = deadline - time.monotonic()
            if not pending or remaining <= 0:
                break
            self._result_ready.wait(min(0.05, remaining))
        self._closed = True
        self._drained = not pending and not unresolved
        for delivery in pending:
            delivery.state = "UNKNOWN" if delivery.state == "SENDING" else "FAILED"
            delivery.error = "Cierre sin confirmación del envío" if delivery.state == "UNKNOWN" else "Cierre antes del reintento"
            delivery.next_retry_at = None
            self._publish(delivery)
        self._stop.set()
        self._tasks.put(None)
        if self._thread is not None:
            self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
        if pending:
            LOG.warning("Cierre con %d notificaciones pendientes; no se confirmó su finalización", len(pending))
        if unresolved:
            LOG.warning("Cierre con destinatario sin resolver; la alerta pendiente no se envió")
        return self._drained
