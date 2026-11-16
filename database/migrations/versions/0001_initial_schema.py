"""Crear las cinco tablas iniciales de CareWatch"""

from alembic import op
import sqlalchemy as sa


revision = 'b69c792f1e6a'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("btrim(code) <> ''", name=op.f('ck_users_code_not_empty')),
        sa.CheckConstraint("btrim(name) <> ''", name=op.f('ck_users_name_not_empty')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
        sa.UniqueConstraint('code', name=op.f('uq_users_code'))
    )
    op.create_table('fall_episodes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('source_kind', sa.Text(), nullable=False),
        sa.Column('criterion', sa.Text(), nullable=False),
        sa.Column('detector_state', sa.Text(), nullable=False),
        sa.Column('tracking_status', sa.Text(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('on_floor_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('recovered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('close_reason', sa.Text(), nullable=True),
        sa.Column('floor_seconds', sa.Double(), server_default=sa.text('0'), nullable=False),
        sa.Column('alert_state', sa.Text(), nullable=True),
        sa.Column('cancel_seconds', sa.Double(), nullable=True),
        sa.Column('remaining_seconds', sa.Double(), nullable=True),
        sa.Column('paused', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('paused_seconds', sa.Double(), server_default=sa.text('0'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("NOT paused OR (alert_state IS NOT NULL AND alert_state = 'COUNTDOWN' AND cancel_seconds IS NOT NULL AND paused_seconds < cancel_seconds AND remaining_seconds IS NOT NULL AND remaining_seconds > 0)", name=op.f('ck_fall_episodes_pause_consistency')),
        sa.CheckConstraint("alert_state IN ('IDLE', 'COUNTDOWN', 'CANCELLED', 'READY')", name=op.f('ck_fall_episodes_alert_state')),
        sa.CheckConstraint("cancel_seconds > 0 AND cancel_seconds < 'Infinity'::float8", name=op.f('ck_fall_episodes_cancel_seconds')),
        sa.CheckConstraint("close_reason IN ('recovered', 'discarded', 'run_ended')", name=op.f('ck_fall_episodes_close_reason')),
        sa.CheckConstraint("criterion IN ('rapid_descent', 'posture_change', 'persistent_posture')", name=op.f('ck_fall_episodes_criterion')),
        sa.CheckConstraint("detector_state IN ('NO_PERSON', 'UNKNOWN', 'STANDING', 'FALLING', 'ON_FLOOR', 'RECOVERING', 'RECOVERED')", name=op.f('ck_fall_episodes_detector_state')),
        sa.CheckConstraint("floor_seconds >= 0 AND floor_seconds < 'Infinity'::float8", name=op.f('ck_fall_episodes_floor_seconds')),
        sa.CheckConstraint("paused_seconds >= 0 AND paused_seconds < 'Infinity'::float8 AND (cancel_seconds IS NULL OR paused_seconds <= cancel_seconds)", name=op.f('ck_fall_episodes_paused_seconds')),
        sa.CheckConstraint("remaining_seconds >= 0 AND remaining_seconds < 'Infinity'::float8", name=op.f('ck_fall_episodes_remaining_seconds')),
        sa.CheckConstraint("source_kind IN ('camera', 'video')", name=op.f('ck_fall_episodes_source_kind')),
        sa.CheckConstraint("tracking_status IN ('VALID', 'ABSENT', 'INVALID', 'LOST')", name=op.f('ck_fall_episodes_tracking_status')),
        sa.CheckConstraint('(closed_at IS NULL) = (close_reason IS NULL)', name=op.f('ck_fall_episodes_closure_consistency')),
        sa.CheckConstraint('closed_at IS NULL OR closed_at >= started_at', name=op.f('ck_fall_episodes_closed_order')),
        sa.CheckConstraint('confirmed_at IS NULL OR (on_floor_at IS NOT NULL AND confirmed_at >= on_floor_at)', name=op.f('ck_fall_episodes_confirmed_order')),
        sa.CheckConstraint('on_floor_at IS NULL OR on_floor_at >= started_at', name=op.f('ck_fall_episodes_on_floor_order')),
        sa.CheckConstraint('recovered_at IS NULL OR recovered_at >= started_at', name=op.f('ck_fall_episodes_recovered_order')),
        sa.CheckConstraint('remaining_seconds IS NULL OR (cancel_seconds IS NOT NULL AND remaining_seconds <= cancel_seconds)', name=op.f('ck_fall_episodes_remaining_within_countdown')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_fall_episodes_user_id_users'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_fall_episodes'))
    )
    op.create_index(op.f('ix_fall_episodes_run_id'), 'fall_episodes', ['run_id'], unique=False)
    op.create_index('ix_fall_episodes_user_started', 'fall_episodes', ['user_id', 'started_at'], unique=False)
    op.create_table('trusted_contacts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('telegram_chat_id', sa.Text(), nullable=True),
        sa.Column('notifications_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("btrim(name) <> ''", name=op.f('ck_trusted_contacts_name_not_empty')),
        sa.CheckConstraint("telegram_chat_id IS NULL OR btrim(telegram_chat_id) <> ''", name=op.f('ck_trusted_contacts_chat_id_not_empty')),
        sa.CheckConstraint('NOT notifications_enabled OR telegram_chat_id IS NOT NULL', name=op.f('ck_trusted_contacts_enabled_has_chat_id')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_trusted_contacts_user_id_users'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_trusted_contacts')),
        sa.UniqueConstraint('user_id', 'telegram_chat_id', name=op.f('uq_trusted_contacts_user_id'))
    )
    op.create_index(op.f('ix_trusted_contacts_user_id'), 'trusted_contacts', ['user_id'], unique=False)
    op.create_table('episode_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('episode_id', sa.Uuid(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('source_timestamp', sa.Double(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('floor_seconds', sa.Double(), server_default=sa.text('0'), nullable=False),
        sa.CheckConstraint("floor_seconds >= 0 AND floor_seconds < 'Infinity'::float8", name=op.f('ck_episode_events_floor_seconds')),
        sa.CheckConstraint("source_timestamp >= 0 AND source_timestamp < 'Infinity'::float8", name=op.f('ck_episode_events_source_timestamp')),
        sa.CheckConstraint("type IN ('person_detected', 'person_lost', 'fall_started', 'fall_suspected', 'person_on_floor', 'fall_confirmed', 'person_recovered')", name=op.f('ck_episode_events_type')),
        sa.ForeignKeyConstraint(['episode_id'], ['fall_episodes.id'], name=op.f('fk_episode_events_episode_id_fall_episodes'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_episode_events'))
    )
    op.create_index(op.f('ix_episode_events_episode_id'), 'episode_events', ['episode_id'], unique=False)
    op.create_table('notifications',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('episode_id', sa.Uuid(), nullable=False),
        sa.Column('contact_id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('telegram_chat_id', sa.Text(), nullable=False),
        sa.Column('message_text', sa.Text(), nullable=False),
        sa.Column('state', sa.Text(), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("(state = 'SENT') = (accepted_at IS NOT NULL)", name=op.f('ck_notifications_accepted_consistency')),
        sa.CheckConstraint("btrim(message_text) <> ''", name=op.f('ck_notifications_message_not_empty')),
        sa.CheckConstraint("btrim(telegram_chat_id) <> ''", name=op.f('ck_notifications_chat_id_not_empty')),
        sa.CheckConstraint("kind IN ('alert', 'recovery')", name=op.f('ck_notifications_kind')),
        sa.CheckConstraint("state <> 'RETRY' OR next_retry_at IS NOT NULL", name=op.f('ck_notifications_retry_has_date')),
        sa.CheckConstraint("state IN ('SENDING', 'RETRY', 'SENT', 'FAILED', 'UNKNOWN')", name=op.f('ck_notifications_state')),
        sa.CheckConstraint('accepted_at IS NULL OR accepted_at >= created_at', name=op.f('ck_notifications_accepted_order')),
        sa.CheckConstraint('attempts BETWEEN 0 AND 3', name=op.f('ck_notifications_attempts')),
        sa.CheckConstraint('last_attempt_at IS NULL OR last_attempt_at >= created_at', name=op.f('ck_notifications_attempt_order')),
        sa.ForeignKeyConstraint(['contact_id'], ['trusted_contacts.id'], name=op.f('fk_notifications_contact_id_trusted_contacts'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['episode_id'], ['fall_episodes.id'], name=op.f('fk_notifications_episode_id_fall_episodes'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications')),
        sa.UniqueConstraint('episode_id', 'contact_id', 'kind', name=op.f('uq_notifications_episode_id'))
    )
    op.create_index(op.f('ix_notifications_contact_id'), 'notifications', ['contact_id'], unique=False)
    op.create_index(op.f('ix_notifications_episode_id'), 'notifications', ['episode_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_notifications_episode_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_contact_id'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_episode_events_episode_id'), table_name='episode_events')
    op.drop_table('episode_events')
    op.drop_index(op.f('ix_trusted_contacts_user_id'), table_name='trusted_contacts')
    op.drop_table('trusted_contacts')
    op.drop_index('ix_fall_episodes_user_started', table_name='fall_episodes')
    op.drop_index(op.f('ix_fall_episodes_run_id'), table_name='fall_episodes')
    op.drop_table('fall_episodes')
    op.drop_table('users')
