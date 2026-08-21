"""add admin role and suspension fields

Revision ID: da39efd1e412
Revises: eec36154bc48
Create Date: 2026-08-21 02:23:14.969591

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da39efd1e412'
down_revision: Union[str, Sequence[str], None] = 'eec36154bc48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOTE: autogenerate also proposed loosening bookings.paid/lesson_requests.paid
    # back to nullable=True here — same SQLite NOT NULL reflection quirk as
    # every prior migration since b623b8113c95, not real drift. Deliberately dropped.
    op.create_table('admins',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('hashed_password', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_admins_email'), 'admins', ['email'], unique=True)
    op.create_index(op.f('ix_admins_id'), 'admins', ['id'], unique=False)
    # nullable=False + server_default=false(), not the bare nullable=True
    # autogenerate proposed — same reasoning as `paid` in cd44acd0a348:
    # every *new* row gets suspended=False for free from the ORM's
    # default=False, but existing rows need a real backfilled value here,
    # or `.filter(Instructor.suspended.is_(False))` would wrongly exclude
    # them (SQL NULL IS FALSE is FALSE, not a match).
    op.add_column('customers', sa.Column('suspended', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('customers', sa.Column('suspension_reason', sa.Text(), nullable=True))
    op.add_column('instructors', sa.Column('suspended', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('instructors', sa.Column('suspension_reason', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('instructors', 'suspension_reason')
    op.drop_column('instructors', 'suspended')
    op.drop_column('customers', 'suspension_reason')
    op.drop_column('customers', 'suspended')
    op.drop_index(op.f('ix_admins_id'), table_name='admins')
    op.drop_index(op.f('ix_admins_email'), table_name='admins')
    op.drop_table('admins')
