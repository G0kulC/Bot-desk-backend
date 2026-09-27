"""webhook events

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('webhook_events',
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('event_key', sa.String(length=255), nullable=False),
    sa.Column('client_id', sa.UUID(), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], name=op.f('fk_webhook_events_client_id_clients'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_webhook_events')),
    sa.UniqueConstraint('event_key', name=op.f('uq_webhook_events_event_key'))
    )
    op.create_index(op.f('ix_webhook_events_client_id'), 'webhook_events', ['client_id'], unique=False)


def downgrade() -> None:
    op.drop_table('webhook_events')
