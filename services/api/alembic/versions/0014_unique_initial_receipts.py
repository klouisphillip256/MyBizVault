"""Prevent duplicate initial receipts during concurrent historical backfill.

Revision ID: 0014_unique_initial_receipts
Revises: 0013_challenge_delivery
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_unique_initial_receipts"
down_revision = "0013_challenge_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("uq_receipt_initial_transaction", "receipts", ["transaction_id"],
        unique=True, postgresql_where=sa.text("kind = 'initial'"),
        sqlite_where=sa.text("kind = 'initial'"))


def downgrade() -> None:
    op.drop_index("uq_receipt_initial_transaction", table_name="receipts")
