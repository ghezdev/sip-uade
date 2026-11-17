"""Tablas de historial; no intervienen en la detección ni en el envío de mensajes."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Double, ForeignKey, Index, Integer,
    MetaData, Text, UniqueConstraint, Uuid, func, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "pk": "pk_%(table_name)s", "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s", "ck": "ck_%(table_name)s_%(constraint_name)s",
        "ix": "ix_%(table_name)s_%(column_0_name)s",
    })


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("btrim(code) <> ''", name="code_not_empty"),
        CheckConstraint("btrim(name) <> ''", name="name_not_empty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contacts: Mapped[list["TrustedContact"]] = relationship(back_populates="user", passive_deletes="all")
    episodes: Mapped[list["FallEpisode"]] = relationship(back_populates="user", passive_deletes="all")


class TrustedContact(Base):
    __tablename__ = "trusted_contacts"
    __table_args__ = (
        UniqueConstraint("user_id", "telegram_chat_id"),
        CheckConstraint("btrim(name) <> ''", name="name_not_empty"),
        CheckConstraint("telegram_chat_id IS NULL OR btrim(telegram_chat_id) <> ''", name="chat_id_not_empty"),
        CheckConstraint("NOT notifications_enabled OR telegram_chat_id IS NOT NULL", name="enabled_has_chat_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(Text)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(Text)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="contacts")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="contact", passive_deletes="all")


class FallEpisode(Base):
    __tablename__ = "fall_episodes"
    __table_args__ = (
        Index("ix_fall_episodes_user_started", "user_id", "started_at"),
        CheckConstraint("source_kind IN ('camera', 'video')", name="source_kind"),
        CheckConstraint("criterion IN ('rapid_descent', 'posture_change', 'persistent_posture')", name="criterion"),
        CheckConstraint("detector_state IN ('NO_PERSON', 'UNKNOWN', 'STANDING', 'FALLING', 'ON_FLOOR', 'RECOVERING', 'RECOVERED')", name="detector_state"),
        CheckConstraint("tracking_status IN ('VALID', 'ABSENT', 'INVALID', 'LOST')", name="tracking_status"),
        CheckConstraint("alert_state IN ('IDLE', 'COUNTDOWN', 'CANCELLED', 'READY')", name="alert_state"),
        CheckConstraint("close_reason IN ('recovered', 'discarded', 'run_ended')", name="close_reason"),
        CheckConstraint("(closed_at IS NULL) = (close_reason IS NULL)", name="closure_consistency"),
        CheckConstraint("floor_seconds >= 0 AND floor_seconds < 'Infinity'::float8", name="floor_seconds"),
        CheckConstraint("cancel_seconds > 0 AND cancel_seconds < 'Infinity'::float8", name="cancel_seconds"),
        CheckConstraint("remaining_seconds >= 0 AND remaining_seconds < 'Infinity'::float8", name="remaining_seconds"),
        CheckConstraint("paused_seconds >= 0 AND paused_seconds < 'Infinity'::float8 AND (cancel_seconds IS NULL OR paused_seconds <= cancel_seconds)", name="paused_seconds"),
        CheckConstraint("remaining_seconds IS NULL OR (cancel_seconds IS NOT NULL AND remaining_seconds <= cancel_seconds)", name="remaining_within_countdown"),
        CheckConstraint("NOT paused OR (alert_state IS NOT NULL AND alert_state = 'COUNTDOWN' AND cancel_seconds IS NOT NULL AND paused_seconds < cancel_seconds AND remaining_seconds IS NOT NULL AND remaining_seconds > 0)", name="pause_consistency"),
        CheckConstraint("on_floor_at IS NULL OR on_floor_at >= started_at", name="on_floor_order"),
        CheckConstraint("confirmed_at IS NULL OR (on_floor_at IS NOT NULL AND confirmed_at >= on_floor_at)", name="confirmed_order"),
        CheckConstraint("recovered_at IS NULL OR recovered_at >= started_at", name="recovered_order"),
        CheckConstraint("closed_at IS NULL OR closed_at >= started_at", name="closed_order"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    run_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    source_kind: Mapped[str] = mapped_column(Text)
    criterion: Mapped[str] = mapped_column(Text)
    detector_state: Mapped[str] = mapped_column(Text)
    tracking_status: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    on_floor_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    recovered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[Optional[str]] = mapped_column(Text)
    floor_seconds: Mapped[float] = mapped_column(Double, server_default=text("0"))
    alert_state: Mapped[Optional[str]] = mapped_column(Text)
    cancel_seconds: Mapped[Optional[float]] = mapped_column(Double)
    remaining_seconds: Mapped[Optional[float]] = mapped_column(Double)
    paused: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    paused_seconds: Mapped[float] = mapped_column(Double, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="episodes")
    events: Mapped[list["EpisodeEvent"]] = relationship(back_populates="episode", passive_deletes="all")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="episode", passive_deletes="all")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("episode_id", "contact_id", "kind"),
        CheckConstraint("kind IN ('alert', 'recovery')", name="kind"),
        CheckConstraint("state IN ('SENDING', 'RETRY', 'SENT', 'FAILED', 'UNKNOWN')", name="state"),
        CheckConstraint("attempts BETWEEN 0 AND 3", name="attempts"),
        CheckConstraint("btrim(telegram_chat_id) <> ''", name="chat_id_not_empty"),
        CheckConstraint("btrim(message_text) <> ''", name="message_not_empty"),
        CheckConstraint("(state = 'SENT') = (accepted_at IS NOT NULL)", name="accepted_consistency"),
        CheckConstraint("state <> 'RETRY' OR next_retry_at IS NOT NULL", name="retry_has_date"),
        CheckConstraint("accepted_at IS NULL OR accepted_at >= created_at", name="accepted_order"),
        CheckConstraint("last_attempt_at IS NULL OR last_attempt_at >= created_at", name="attempt_order"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    episode_id: Mapped[UUID] = mapped_column(ForeignKey("fall_episodes.id", ondelete="RESTRICT"), index=True)
    contact_id: Mapped[UUID] = mapped_column(ForeignKey("trusted_contacts.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(Text)
    telegram_chat_id: Mapped[str] = mapped_column(Text)
    message_text: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    episode: Mapped[FallEpisode] = relationship(back_populates="notifications")
    contact: Mapped[TrustedContact] = relationship(back_populates="notifications")


class EpisodeEvent(Base):
    __tablename__ = "episode_events"
    __table_args__ = (
        CheckConstraint("type IN ('person_detected', 'person_lost', 'fall_started', 'fall_suspected', 'person_on_floor', 'fall_confirmed', 'person_recovered')", name="type"),
        CheckConstraint("source_timestamp >= 0 AND source_timestamp < 'Infinity'::float8", name="source_timestamp"),
        CheckConstraint("floor_seconds >= 0 AND floor_seconds < 'Infinity'::float8", name="floor_seconds"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    episode_id: Mapped[UUID] = mapped_column(ForeignKey("fall_episodes.id", ondelete="RESTRICT"), index=True)
    type: Mapped[str] = mapped_column(Text)
    source_timestamp: Mapped[float] = mapped_column(Double)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    floor_seconds: Mapped[float] = mapped_column(Double, server_default=text("0"))

    episode: Mapped[FallEpisode] = relationship(back_populates="events")
