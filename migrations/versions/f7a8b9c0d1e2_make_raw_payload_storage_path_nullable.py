"""Make raw_payloads.storage_path nullable.

When the raw JSON backup cannot be saved (e.g. disk unavailable), the collection
should continue — raw payloads are audit trail, not critical path.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-08-30
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7a8b9c0d1e2'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('raw_payloads', 'storage_path',
                     existing_type=sa.String(1024),
                     nullable=True)


def downgrade():
    op.alter_column('raw_payloads', 'storage_path',
                     existing_type=sa.String(1024),
                     nullable=False)
