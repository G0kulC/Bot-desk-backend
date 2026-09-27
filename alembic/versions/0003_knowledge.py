"""knowledge

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('knowledge_bases',
    sa.Column('client_id', sa.UUID(), nullable=False),
    sa.Column('address', sa.Text(), nullable=False),
    sa.Column('timings', sa.Text(), nullable=False),
    sa.Column('services', sa.Text(), nullable=False),
    sa.Column('faqs', sa.Text(), nullable=False),
    sa.Column('booking_instructions', sa.Text(), nullable=False),
    sa.Column('rules', sa.Text(), nullable=False),
    sa.Column('handoff_contact', sa.Text(), nullable=False),
    sa.Column('tone', sa.Text(), nullable=False),
    sa.Column('approved', sa.Boolean(), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approved_by_name', sa.String(length=255), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], name=op.f('fk_knowledge_bases_client_id_clients'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_knowledge_bases')),
    sa.UniqueConstraint('client_id', name=op.f('uq_knowledge_bases_client_id'))
    )
    op.create_table('knowledge_versions',
    sa.Column('knowledge_base_id', sa.UUID(), nullable=False),
    sa.Column('client_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('saved_by', sa.String(length=255), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], name=op.f('fk_knowledge_versions_client_id_clients'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['knowledge_base_id'], ['knowledge_bases.id'], name=op.f('fk_knowledge_versions_knowledge_base_id_knowledge_bases'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_knowledge_versions')),
    sa.UniqueConstraint('knowledge_base_id', 'version', name='uq_knowledge_versions_kb_version')
    )
    op.create_index(op.f('ix_knowledge_versions_client_id'), 'knowledge_versions', ['client_id'], unique=False)
    op.create_index(op.f('ix_knowledge_versions_knowledge_base_id'), 'knowledge_versions', ['knowledge_base_id'], unique=False)


def downgrade() -> None:
    op.drop_table('knowledge_versions')
    op.drop_table('knowledge_bases')
