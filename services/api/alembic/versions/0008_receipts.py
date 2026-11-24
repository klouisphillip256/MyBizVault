"""Store immutable receipt facts without changing historical transactions.

Revision ID: 0008_receipts
Revises: 0007_proposal_invitations
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_receipts"
down_revision = "0007_proposal_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("businesses", sa.Column("phone", sa.String(32)))
    op.add_column("businesses", sa.Column("email", sa.String(254)))
    op.create_table("receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("payment_id", sa.String(36), sa.ForeignKey("payment_records.id")),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("payment_id", name="uq_receipt_payment"))
    op.create_index("ix_receipts_business_id", "receipts", ["business_id"])
    op.create_index("ix_receipts_transaction_id", "receipts", ["transaction_id"])


def downgrade() -> None:
    op.drop_table("receipts")
    op.drop_column("businesses", "email")
    op.drop_column("businesses", "phone")
