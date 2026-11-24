"""Track provider submissions and verified delivery callbacks.

Revision ID: 0010_communication_logs
Revises: 0009_database_storage
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_communication_logs"
down_revision = "0009_database_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("communication_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("agreement_id", sa.String(36), sa.ForeignKey("agreements.id")),
        sa.Column("proposal_id", sa.String(36), sa.ForeignKey("negotiation_records.id")),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_message_id", sa.String(180)),
        sa.Column("recipient_masked", sa.String(254), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("detail", sa.String(300)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_communication_logs_business_transaction", "communication_logs",
        ["business_id", "transaction_id"])


def downgrade() -> None:
    op.drop_table("communication_logs")
