"""conversations

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('contacts',
    sa.Column('client_id', sa.UUID(), nullable=False),
    sa.Column('wa_id', sa.String(length=32), nullable=False),
    sa.Column('profile_name', sa.String(length=255), nullable=True),
    sa.Column('detected_language', sa.String(length=32), nullable=True),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_inbound_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('handoff_active', sa.Boolean(), nullable=False),
    sa.Column('handoff_since', sa.DateTime(timezone=True), nullable=True),
    sa.Column('handoff_reason', sa.Text(), nullable=True),
    sa.Column('opted_out', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], name=op.f('fk_contacts_client_id_clients'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_contacts')),
    sa.UniqueConstraint('client_id', 'wa_id', name='uq_contacts_client_wa')
    )
    op.create_index(op.f('ix_contacts_client_id'), 'contacts', ['client_id'], unique=False)
    op.create_table('messages',
    sa.Column('client_id', sa.UUID(), nullable=False),
    sa.Column('contact_id', sa.UUID(), nullable=False),
    sa.Column('direction', sa.Enum('in', 'out', name='direction', native_enum=False, length=32), nullable=False),
    sa.Column('sender', sa.Enum('customer', 'bot', 'agent', 'system', name='sender', native_enum=False, length=32), nullable=False),
    sa.Column('provider', sa.Enum('own', 'aisensy', name='provider', native_enum=False, length=32), nullable=True),
    sa.Column('provider_message_id', sa.String(length=255), nullable=True),
    sa.Column('msg_type', sa.Enum('text', 'image', 'audio', 'location', 'template', 'other', name='msg_type', native_enum=False, length=32), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('received', 'sent', 'delivered', 'read', 'failed', name='msg_status', native_enum=False, length=32), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('ai_model', sa.String(length=128), nullable=True),
    sa.Column('tokens_in', sa.Integer(), nullable=True),
    sa.Column('tokens_out', sa.Integer(), nullable=True),
    sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], name=op.f('fk_messages_client_id_clients'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], name=op.f('fk_messages_contact_id_contacts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages'))
    )
    op.create_index('ix_messages_client_created', 'messages', ['client_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_messages_client_id'), 'messages', ['client_id'], unique=False)
    op.create_index('ix_messages_contact_created', 'messages', ['contact_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_messages_contact_id'), 'messages', ['contact_id'], unique=False)
    op.create_index('uq_messages_provider_message_id', 'messages', ['provider_message_id'], unique=True, postgresql_where=sa.text('provider_message_id IS NOT NULL'))
    op.create_table('leads',
    sa.Column('client_id', sa.UUID(), nullable=False),
    sa.Column('contact_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('phone', sa.String(length=32), nullable=False),
    sa.Column('need', sa.Text(), nullable=False),
    sa.Column('preferred_time', sa.String(length=255), nullable=False),
    sa.Column('status', sa.Enum('new', 'contacted', 'won', 'lost', name='lead_status', native_enum=False, length=32), nullable=False),
    sa.Column('source_message_id', sa.UUID(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], name=op.f('fk_leads_client_id_clients'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], name=op.f('fk_leads_contact_id_contacts'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['source_message_id'], ['messages.id'], name=op.f('fk_leads_source_message_id_messages'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_leads'))
    )
    op.create_index(op.f('ix_leads_client_id'), 'leads', ['client_id'], unique=False)
    op.create_index(op.f('ix_leads_contact_id'), 'leads', ['contact_id'], unique=False)
    op.create_index(op.f('ix_leads_source_message_id'), 'leads', ['source_message_id'], unique=False)




def downgrade() -> None:
    op.drop_table('leads')
    op.drop_table('messages')
    op.drop_table('contacts')
