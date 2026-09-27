"""payments

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('payments',
    sa.Column('client_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.Enum('setup', 'monthly', 'other', name='payment_type', native_enum=False, length=32), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('for_month', sa.Date(), nullable=True),
    sa.Column('paid_on', sa.Date(), nullable=False),
    sa.Column('method', sa.Enum('UPI', 'cash', 'bank', 'card', name='payment_method', native_enum=False, length=32), nullable=False),
    sa.Column('reference', sa.String(length=255), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], name=op.f('fk_payments_client_id_clients'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payments'))
    )
    op.create_index('ix_payments_client_for_month', 'payments', ['client_id', 'for_month'], unique=False)
    op.create_index(op.f('ix_payments_client_id'), 'payments', ['client_id'], unique=False)


def downgrade() -> None:
    op.drop_table('payments')
