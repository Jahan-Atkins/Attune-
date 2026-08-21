"""add recurring bookings

Revision ID: eec36154bc48
Revises: 61908be0a3e1
Create Date: 2026-08-21 01:59:44.381430

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eec36154bc48'
down_revision: Union[str, Sequence[str], None] = '61908be0a3e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOTE: autogenerate also proposed loosening bookings.paid/lesson_requests.paid
    # back to nullable=True here — same SQLite NOT NULL reflection quirk as
    # migrations b623b8113c95, d6381830b851, and 61908be0a3e1, not real drift.
    # Deliberately dropped.
    #
    # batch_alter_table (not plain op.add_column/op.create_foreign_key) is
    # required for the two ALTERs below that add a new FK constraint — see
    # 61908be0a3e1's upgrade() for why. create_table itself doesn't need it.
    op.create_table('recurring_series',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('instructor_id', sa.Integer(), nullable=False),
    sa.Column('specialty', sa.String(), nullable=False),
    sa.Column('duration_minutes', sa.Integer(), nullable=False),
    sa.Column('day_of_week', sa.Integer(), nullable=False),
    sa.Column('start_time', sa.String(), nullable=False),
    sa.Column('end_time', sa.String(), nullable=False),
    sa.Column('price_per_lesson', sa.Float(), nullable=False),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['instructor_id'], ['instructors.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recurring_series_id'), 'recurring_series', ['id'], unique=False)

    with op.batch_alter_table('clients') as batch_op:
        batch_op.add_column(sa.Column('customer_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_clients_customer_id', 'customers', ['customer_id'], ['id'])
    with op.batch_alter_table('lesson_requests') as batch_op:
        batch_op.add_column(sa.Column('recurring_series_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('occurrence_date', sa.String(), nullable=True))
        batch_op.create_foreign_key('fk_lesson_requests_recurring_series_id', 'recurring_series', ['recurring_series_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('lesson_requests') as batch_op:
        batch_op.drop_constraint('fk_lesson_requests_recurring_series_id', type_='foreignkey')
        batch_op.drop_column('occurrence_date')
        batch_op.drop_column('recurring_series_id')
    with op.batch_alter_table('clients') as batch_op:
        batch_op.drop_constraint('fk_clients_customer_id', type_='foreignkey')
        batch_op.drop_column('customer_id')

    op.drop_index(op.f('ix_recurring_series_id'), table_name='recurring_series')
    op.drop_table('recurring_series')
