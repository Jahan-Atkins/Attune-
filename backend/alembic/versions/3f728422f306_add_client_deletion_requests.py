"""add client deletion requests

Revision ID: 3f728422f306
Revises: da39efd1e412
Create Date: 2026-08-21 09:38:50.171531

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f728422f306'
down_revision: Union[str, Sequence[str], None] = 'da39efd1e412'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOTE: autogenerate also proposed loosening bookings.paid/lesson_requests.paid/
    # customers.suspended/instructors.suspended back to nullable=True here —
    # same SQLite NOT NULL reflection quirk as every prior migration since
    # b623b8113c95, not real drift. Deliberately dropped.
    op.create_table('client_deletion_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('instructor_id', sa.Integer(), nullable=False),
    sa.Column('requested_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['instructor_id'], ['instructors.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_client_deletion_requests_id'), 'client_deletion_requests', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_client_deletion_requests_id'), table_name='client_deletion_requests')
    op.drop_table('client_deletion_requests')
