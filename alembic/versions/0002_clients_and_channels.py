"""clients and channels

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('clients',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('niche', sa.Enum('dental_clinic', 'skin_clinic', 'salon', 'coaching_centre', 'gym', 'bakery_sweets', 'real_estate', 'restaurant', 'other', name='niche', native_enum=False, length=32), nullable=False),
    sa.Column('city', sa.String(length=128), nullable=False),
    sa.Column('owner_name', sa.String(length=255), nullable=False),
    sa.Column('owner_phone', sa.String(length=20), nullable=True),
    sa.Column('status', sa.Enum('lead', 'trial', 'live', 'paused', name='client_status', native_enum=False, length=32), nullable=False),
    sa.Column('package', sa.Enum('starter', 'business', 'growth', 'custom', name='package', native_enum=False, length=32), nullable=False),
    sa.Column('setup_fee', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('monthly_fee', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('trial_start', sa.Date(), nullable=True),
    sa.Column('live_date', sa.Date(), nullable=True),
    sa.Column('languages', sa.ARRAY(sa.Text()), server_default=sa.text("'{English}'"), nullable=False),
    sa.Column('provider_override', sa.Enum('own', 'aisensy', name='provider', native_enum=False, length=32), nullable=True),
    sa.Column('bot_enabled', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clients'))
    )
    op.create_index('ix_clients_status', 'clients', ['status'], unique=False)
    op.create_table('client_channels',
    sa.Column('client_id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.Enum('own', 'aisensy', name='provider', native_enum=False, length=32), nullable=False),
    sa.Column('display_phone', sa.String(length=20), nullable=True),
    sa.Column('meta_phone_number_id', sa.String(length=64), nullable=True),
    sa.Column('meta_waba_id', sa.String(length=64), nullable=True),
    sa.Column('meta_access_token_enc', sa.Text(), nullable=True),
    sa.Column('aisensy_project_id', sa.String(length=128), nullable=True),
    sa.Column('aisensy_api_key_enc', sa.Text(), nullable=True),
    sa.Column('aisensy_webhook_secret_enc', sa.Text(), nullable=True),
    sa.Column('channel_token', sa.String(length=64), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_inbound_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], name=op.f('fk_client_channels_client_id_clients'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_client_channels')),
    sa.UniqueConstraint('channel_token', name=op.f('uq_client_channels_channel_token'))
    )
    op.create_index(op.f('ix_client_channels_client_id'), 'client_channels', ['client_id'], unique=False)
    op.create_index('uq_client_channels_active_client', 'client_channels', ['client_id'], unique=True, postgresql_where=sa.text('is_active'))
    op.create_index('uq_client_channels_meta_phone_number_id', 'client_channels', ['meta_phone_number_id'], unique=True, postgresql_where=sa.text('meta_phone_number_id IS NOT NULL'))
    op.create_table('attention_items',
    sa.Column('client_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('dedupe_key', sa.String(length=128), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], name=op.f('fk_attention_items_client_id_clients'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attention_items')),
    sa.UniqueConstraint('dedupe_key', name=op.f('uq_attention_items_dedupe_key'))
    )
    op.create_index(op.f('ix_attention_items_client_id'), 'attention_items', ['client_id'], unique=False)


def downgrade() -> None:
    op.drop_table('attention_items')
    op.drop_table('client_channels')
    op.drop_table('clients')
