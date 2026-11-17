"""Convierte observaciones y resultados de envío en registros de una ejecución."""

from contextlib import contextmanager
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from alerts.notifications import Recipient
from fall_detection.models import DetectorState, EventType
from services.contacts import select_contact
from .connection import create_db_engine
from . import repositories


class EpisodeStore:
    """Una sesión por transacción; esta instancia pertenece solo al worker."""

    def __init__(self, source_kind, cancel_seconds, *, engine=None):
        self.engine = engine if engine is not None else create_db_engine()
        self.run_id = uuid4()
        self.source_kind = source_kind
        self.cancel_seconds = cancel_seconds
        self._active_id = None
        try:
            with self._transaction() as session:
                self.user_id = repositories.get_user_id_by_code(session, "demo")
                if self.user_id is None:
                    raise LookupError("No existe el usuario demo. Ejecutá: python -m database.seed")
        except Exception:
            self.engine.dispose()
            raise

    @contextmanager
    def _transaction(self):
        with Session(self.engine) as session, session.begin():
            session.execute(text("SET LOCAL statement_timeout = '2s'"))
            session.execute(text("SET LOCAL lock_timeout = '1s'"))
            yield session

    def write(self, result, alert, observed_at):
        current_id = UUID(result.episode_id) if result.episode_id else None
        episode_ids = dict.fromkeys(event.episode_id for event in result.events if event.episode_id)
        if result.episode_id:
            episode_ids[result.episode_id] = None
        next_active = current_id
        with self._transaction() as session:
            for episode_id in episode_ids:
                identifier = UUID(episode_id)
                episode = repositories.get_episode(session, identifier)
                events = [event for event in result.events if event.episode_id == episode_id]
                if episode is None:
                    if identifier != current_id or result.criterion is None:
                        raise ValueError("No hay datos de inicio para el episodio observado")
                    episode = repositories.add_episode(session,
                        id=identifier, user_id=self.user_id, run_id=self.run_id,
                        source_kind=self.source_kind, criterion=result.criterion.value,
                        detector_state=result.state.value, tracking_status=result.tracking.value,
                        started_at=observed_at,
                    )
                if episode.run_id != self.run_id:
                    raise ValueError("El episodio pertenece a otra ejecución")
                was_open = episode.closed_at is None
                if was_open:
                    floor_seconds = max([episode.floor_seconds] + [event.floor_seconds for event in events])
                    if identifier == current_id:
                        episode.detector_state = result.state.value
                        episode.tracking_status = result.tracking.value
                        floor_seconds = max(floor_seconds, result.metrics.floor_seconds)
                    episode.floor_seconds = floor_seconds
                    episode.updated_at = observed_at
                    for event in events:
                        if event.type == EventType.PERSON_ON_FLOOR and episode.on_floor_at is None:
                            episode.on_floor_at = observed_at
                        elif event.type == EventType.FALL_CONFIRMED and episode.confirmed_at is None:
                            episode.confirmed_at = observed_at
                        elif event.type == EventType.PERSON_RECOVERED and episode.recovered_at is None:
                            episode.recovered_at = observed_at
                            episode.closed_at = observed_at
                            episode.close_reason = "recovered"
                            episode.detector_state = DetectorState.RECOVERED.value
                    if alert.episode_id == episode_id:
                        episode.alert_state = alert.state.value
                        episode.cancel_seconds = self.cancel_seconds
                        episode.remaining_seconds = alert.remaining_seconds
                        episode.paused = alert.paused
                        episode.paused_seconds = alert.paused_seconds
                session.flush()
                for event in events:
                    repositories.add_event(session, identifier, event, observed_at)
            if self._active_id is not None and self._active_id != current_id:
                previous = repositories.get_episode(session, self._active_id)
                if previous is not None and previous.closed_at is None:
                    if (previous.criterion == "rapid_descent" and previous.on_floor_at is None
                            and previous.confirmed_at is None):
                        previous.closed_at = observed_at
                        previous.close_reason = "discarded"
                        previous.updated_at = observed_at
                    elif current_id is None:
                        next_active = self._active_id
        self._active_id = next_active

    def select_recipient(self):
        with self._transaction() as session:
            contact, reason = select_contact(session, self.user_id)
            recipient = Recipient(contact.id, contact.telegram_chat_id.strip()) if contact is not None else None
            return recipient, reason

    def write_notification(self, delivery):
        recipient = delivery.recipient
        if recipient is None or recipient.contact_id is None:
            return
        with self._transaction() as session:
            episode = repositories.get_episode(session, UUID(delivery.episode_id))
            contact = repositories.get_contact(session, recipient.contact_id)
            if (episode is None or episode.run_id != self.run_id or episode.user_id != self.user_id
                    or contact is None or contact.user_id != self.user_id):
                raise ValueError("El episodio y el contacto deben pertenecer al usuario de esta ejecución")
            repositories.upsert_notification(session, episode.id, contact.id, delivery)

    def finish(self, observed_at):
        if self._active_id is None:
            return
        with self._transaction() as session:
            episode = repositories.get_episode(session, self._active_id)
            if (episode is not None and episode.run_id == self.run_id
                    and episode.closed_at is None and episode.recovered_at is None):
                episode.closed_at = observed_at
                episode.close_reason = "run_ended"
                episode.updated_at = observed_at

    def dispose(self):
        self.engine.dispose()
