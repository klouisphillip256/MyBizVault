"""Private database-backed object bytes for ephemeral deployments.

Revision ID: 0009_database_storage
Revises: 0008_receipts
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_database_storage"
down_revision = "0008_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("stored_objects",
        sa.Column("key", sa.String(300), primary_key=True),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table("stored_objects")
