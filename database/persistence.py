"""Observación de episodios y escrituras en un hilo separado del detector."""

from datetime import datetime, timezone
import logging
from queue import Empty, Full, Queue
from threading import Event, Thread
import time

from sqlalchemy.exc import OperationalError

from alerts.notifications import Recipient
from services.contacts import valid_chat_id
from .recording import EpisodeStore


LOG = logging.getLogger("carewatch.persistence")


class EpisodePersistence:
    def __init__(self, source_kind, cancel_seconds, *, store_factory=EpisodeStore,
                 queue_size=256, clock=time.monotonic, recipient_selection=None, fallback_chat_id=None):
        self._source_kind = source_kind
        self._cancel_seconds = cancel_seconds
        self._store_factory = store_factory
        self._selection = recipient_selection
        self._fallback_chat_id = fallback_chat_id
        self._clock = clock
        self._tasks = Queue(maxsize=queue_size)
        self._disabled = Event()
        self._stop = Event()
        self._closing = Event()
        self._closed_at = None
        self._latest = None
        self._last_sent = None
        self._last_summary = None
        self._last_write = None
        self._previous_episode = None
        self._thread = Thread(target=self._work, name="carewatch-postgres", daemon=True)
        self._thread.start()

    def _disable(self, reason):
        if not self._disabled.is_set():
            self._disabled.set()
            self._stop.set()
            LOG.error("Persistencia deshabilitada: %s. Los nuevos episodios y eventos no se guardarán "
                      "hasta reiniciar CareWatch; puede haber escrituras pendientes sin guardar.", reason)

    def _work(self):
        store = None
        initialized = False
        try:
            store = self._store_factory(self._source_kind, self._cancel_seconds)
            if self._selection is not None:
                recipient, reason = store.select_recipient()
                self._selection.complete(recipient, reason)
                LOG.info("%s", reason)
            initialized = True
            if self._stop.is_set():
                return
            LOG.info("Persistencia habilitada para el usuario demo")
            while not self._stop.is_set():
                try:
                    kind, item = self._tasks.get(timeout=0.05)
                except Empty:
                    if self._closing.is_set():
                        store.finish(self._closed_at)
                        return
                    continue
                if self._stop.is_set():
                    return
                if kind == "episode":
                    store.write(*item)
                else:
                    store.write_notification(item)
        except LookupError:
            if self._selection is not None:
                self._selection.complete(None, "No existe el usuario demo; notificaciones deshabilitadas")
            self._disable("no se encontró el usuario demo; ejecutá python -m database.seed")
        except Exception as exc:
            if self._selection is not None and not self._selection.ready.is_set():
                recipient = None
                reason = "No se pudo seleccionar un contacto; notificaciones deshabilitadas"
                if not initialized and isinstance(exc, (OperationalError, OSError)):
                    if valid_chat_id(self._fallback_chat_id):
                        recipient = Recipient(None, self._fallback_chat_id.strip())
                        reason = "PostgreSQL no disponible: respaldo TELEGRAM_CHAT_ID activo, sin historial persistente de notificaciones"
                    else:
                        reason = "PostgreSQL no disponible y sin respaldo válido; notificaciones deshabilitadas"
                self._selection.complete(recipient, reason)
                LOG.warning("%s", reason)
            # Los errores del controlador pueden contener la URL de conexión.
            self._disable("no se pudo conectar o completar una escritura en PostgreSQL")
        finally:
            if store is not None:
                try:
                    store.dispose()
                except Exception:
                    self._disable("no se pudo cerrar la conexión de persistencia")

    def _enqueue(self, item, kind="episode"):
        try:
            self._tasks.put_nowait((kind, item))
            if kind == "episode":
                self._last_sent = item
        except Full:
            self._disable("la cola de escrituras está llena")

    def observe(self, result, alert):
        if self._disabled.is_set() or self._closing.is_set():
            return
        relevant = (result.episode_id or self._previous_episode
                    or any(event.episode_id for event in result.events))
        self._previous_episode = result.episode_id
        if not relevant:
            return
        self._latest = (result, alert, datetime.now(timezone.utc))
        summary = (result.episode_id, result.state, result.tracking, result.criterion,
                   alert.episode_id, alert.state, alert.paused, alert.pause_exhausted)
        now = self._clock()
        if (result.events or summary != self._last_summary or self._last_write is None
                or now - self._last_write >= 1):
            self._enqueue(self._latest)
            self._last_summary = summary
            self._last_write = now

    def record_notification(self, delivery):
        if self._disabled.is_set() or self._closing.is_set():
            return
        if delivery.recipient is not None and delivery.recipient.contact_id is not None:
            self._enqueue(delivery, "notification")

    def request_close(self):
        if self._closing.is_set():
            return
        self._closed_at = datetime.now(timezone.utc)
        if not self._disabled.is_set() and self._latest is not None and self._latest is not self._last_sent:
            self._enqueue(self._latest)
        self._closing.set()

    def close(self, timeout=3.0):
        self.request_close()
        self._thread.join(timeout=max(0.0, min(3.0, timeout)))
        if self._thread.is_alive():
            self._disable("se agotaron los tres segundos de cierre; la escritura en curso podría terminar después")
            return False
        return not self._disabled.is_set()
