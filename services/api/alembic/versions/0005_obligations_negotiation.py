"""Business-recorded payments, proposals, disputes and their history.

Revision ID: 0005_obligations_negotiation
Revises: 0004_document_vault
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_obligations_negotiation"
down_revision = "0004_document_vault"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("business_memberships", sa.Column("can_manage_obligations", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("payment_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("amount_ugx", sa.Integer(), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(120)), sa.Column("note", sa.Text()),
        sa.Column("evidence_document_id", sa.String(36), sa.ForeignKey("documents.id")),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_ugx > 0", name="ck_payment_amount_positive"))
    op.create_index("ix_payment_records_business_id", "payment_records", ["business_id"])
    op.create_index("ix_payment_records_transaction_id", "payment_records", ["transaction_id"])
    op.create_table("negotiation_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("proposal", sa.Text(), nullable=False),
        sa.Column("proposed_due_date", sa.Date()),
        sa.Column("proposed_amount_ugx", sa.Integer()),
        sa.Column("evidence_document_id", sa.String(36), sa.ForeignKey("documents.id")),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_negotiation_records_business_id", "negotiation_records", ["business_id"])
    op.create_index("ix_negotiation_records_transaction_id", "negotiation_records", ["transaction_id"])
    op.create_table("obligation_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("payment_id", sa.String(36), sa.ForeignKey("payment_records.id")),
        sa.Column("negotiation_id", sa.String(36), sa.ForeignKey("negotiation_records.id")),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_obligation_events_business_id", "obligation_events", ["business_id"])
    op.create_index("ix_obligation_events_transaction_id", "obligation_events", ["transaction_id"])


def downgrade() -> None:
    op.drop_table("obligation_events")
    op.drop_table("negotiation_records")
    op.drop_table("payment_records")
    op.drop_column("business_memberships", "can_manage_obligations")
