"""add preferred instructor for rebooking

Revision ID: 61908be0a3e1
Revises: d6381830b851
Create Date: 2026-08-21 01:38:20.731337

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '61908be0a3e1'
down_revision: Union[str, Sequence[str], None] = 'd6381830b851'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOTE: autogenerate also proposed loosening bookings.paid/lesson_requests.paid
    # back to nullable=True here — same SQLite NOT NULL reflection quirk as
    # migrations b623b8113c95 and d6381830b851, not real drift. Deliberately dropped.
    #
    # batch_alter_table (not plain op.add_column/op.create_foreign_key) is
    # required here: SQLite can't ALTER a table to add a new foreign key
    # constraint outside of batch mode's copy-and-move strategy. Batch mode
    # is a no-op wrapper on Postgres (production), so this is safe there too.
    with op.batch_alter_table('bookings') as batch_op:
        batch_op.add_column(sa.Column('preferred_instructor_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_bookings_preferred_instructor_id', 'instructors', ['preferred_instructor_id'], ['id'])
    with op.batch_alter_table('lesson_requests') as batch_op:
        batch_op.add_column(sa.Column('preferred_instructor_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_lesson_requests_preferred_instructor_id', 'instructors', ['preferred_instructor_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('lesson_requests') as batch_op:
        batch_op.drop_constraint('fk_lesson_requests_preferred_instructor_id', type_='foreignkey')
        batch_op.drop_column('preferred_instructor_id')
    with op.batch_alter_table('bookings') as batch_op:
        batch_op.drop_constraint('fk_bookings_preferred_instructor_id', type_='foreignkey')
        batch_op.drop_column('preferred_instructor_id')
