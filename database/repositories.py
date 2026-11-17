"""Operaciones PostgreSQL; la sesión y la transacción pertenecen al llamador."""

from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import EpisodeEvent, FallEpisode, Notification, TrustedContact, User


def get_user_by_code(session: Session, code, *, for_update=False):
    statement = select(User).where(User.code == code)
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def get_user_id_by_code(session: Session, code):
    return session.scalar(select(User.id).where(User.code == code))


def get_contact(session: Session, contact_id):
    return session.get(TrustedContact, contact_id)


def get_contact_by_chat_id(session: Session, user_id, chat_id):
    return session.scalar(select(TrustedContact).where(
        TrustedContact.user_id == user_id, TrustedContact.telegram_chat_id == chat_id,
    ))


def get_enabled_contacts(session: Session, user_id):
    return session.scalars(select(TrustedContact).where(
        TrustedContact.user_id == user_id, TrustedContact.notifications_enabled.is_(True),
    ).limit(2)).all()


def get_enabled_contact_ids(session: Session, user_id):
    return session.scalars(select(TrustedContact.id).where(
        TrustedContact.user_id == user_id, TrustedContact.notifications_enabled.is_(True),
    )).all()


def add_contact(session: Session, user_id, name):
    contact = TrustedContact(user_id=user_id, name=name)
    session.add(contact)
    return contact


def get_episode(session: Session, episode_id):
    return session.get(FallEpisode, episode_id)


def add_episode(session: Session, **values):
    episode = FallEpisode(**values)
    session.add(episode)
    session.flush()
    return episode


def add_event(session: Session, episode_id, event, recorded_at):
    session.execute(insert(EpisodeEvent).values(
        id=UUID(event.event_id), episode_id=episode_id, type=event.type.value,
        source_timestamp=event.timestamp, recorded_at=recorded_at,
        floor_seconds=event.floor_seconds,
    ).on_conflict_do_nothing(index_elements=[EpisodeEvent.id]))


def upsert_notification(session: Session, episode_id, contact_id, delivery):
    statement = insert(Notification).values(
        id=delivery.id, episode_id=episode_id, contact_id=contact_id, kind=delivery.kind,
        telegram_chat_id=delivery.recipient.chat_id, message_text=delivery.text, state=delivery.state,
        attempts=delivery.attempts, created_at=delivery.created_at,
        last_attempt_at=delivery.last_attempt_at, accepted_at=delivery.accepted_at,
        next_retry_at=delivery.next_retry_at, last_error=delivery.error or None,
        updated_at=delivery.updated_at,
    )
    excluded = statement.excluded
    session.execute(statement.on_conflict_do_update(
        index_elements=[Notification.episode_id, Notification.contact_id, Notification.kind],
        set_={
            "state": excluded.state, "attempts": excluded.attempts,
            "last_attempt_at": excluded.last_attempt_at, "accepted_at": excluded.accepted_at,
            "next_retry_at": excluded.next_retry_at, "updated_at": excluded.updated_at,
            "last_error": func.coalesce(excluded.last_error, Notification.last_error),
        },
        where=and_(Notification.state != "SENT", Notification.attempts <= excluded.attempts,
                   Notification.updated_at <= excluded.updated_at),
    ))
