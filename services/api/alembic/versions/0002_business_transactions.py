"""Business accounts, memberships, counterparties and transactions.

Revision ID: 0002_business_transactions
Revises: 0001_baseline
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_business_transactions"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("failed_logins", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table("businesses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table("business_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("can_view_transactions", sa.Boolean(), nullable=False),
        sa.Column("can_create_transactions", sa.Boolean(), nullable=False),
        sa.Column("can_manage_customers", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("business_id", "user_id", name="uq_membership_business_user"),
    )
    op.create_index("ix_business_memberships_business_id", "business_memberships", ["business_id"])
    op.create_index("ix_business_memberships_user_id", "business_memberships", ["user_id"])
    op.create_table("sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_table("counterparties",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("phone", sa.String(32)),
        sa.Column("email", sa.String(254)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_counterparties_business_id", "counterparties", ["business_id"])
    op.create_index("ix_counterparties_business_name", "counterparties", ["business_id", "display_name"])
    op.create_table("transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("counterparty_id", sa.String(36), sa.ForeignKey("counterparties.id"), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("total_ugx", sa.Integer(), nullable=False),
        sa.Column("paid_ugx", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("delivery_notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("total_ugx > 0", name="ck_transaction_total_positive"),
        sa.CheckConstraint("paid_ugx >= 0 AND paid_ugx <= total_ugx", name="ck_transaction_paid_range"),
    )
    op.create_index("ix_transactions_business_id", "transactions", ["business_id"])
    op.create_index("ix_transactions_counterparty_id", "transactions", ["counterparty_id"])
    op.create_index("ix_transactions_business_date", "transactions", ["business_id", "transaction_date"])


def downgrade() -> None:
    op.drop_table("transactions")
    op.drop_table("counterparties")
    op.drop_table("sessions")
    op.drop_table("business_memberships")
    op.drop_table("businesses")
    op.drop_table("users")
