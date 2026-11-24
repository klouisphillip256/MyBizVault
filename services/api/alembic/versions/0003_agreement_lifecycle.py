"""Versioned credit agreements and external confirmation history.

Revision ID: 0003_agreement_lifecycle
Revises: 0002_business_transactions
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_agreement_lifecycle"
down_revision = "0002_business_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("business_memberships", sa.Column("can_manage_agreements", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("agreements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agreements_business_id", "agreements", ["business_id"])
    op.create_index("ix_agreements_transaction_id", "agreements", ["transaction_id"], unique=True)
    op.create_table("agreement_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agreement_id", sa.String(36), sa.ForeignKey("agreements.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agreement_id", "version", name="uq_agreement_version"),
    )
    op.create_index("ix_agreement_versions_agreement_id", "agreement_versions", ["agreement_id"])
    op.create_table("agreement_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agreement_id", sa.String(36), sa.ForeignKey("agreements.id"), nullable=False),
        sa.Column("agreement_version_id", sa.String(36), sa.ForeignKey("agreement_versions.id"), nullable=False),
        sa.Column("counterparty_id", sa.String(36), sa.ForeignKey("counterparties.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_challenge_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agreement_invitations_agreement_id", "agreement_invitations", ["agreement_id"])
    op.create_index("ix_agreement_invitations_token_hash", "agreement_invitations", ["token_hash"], unique=True)
    op.create_table("confirmation_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invitation_id", sa.String(36), sa.ForeignKey("agreement_invitations.id"), nullable=False),
        sa.Column("code_hash", sa.String(200), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_confirmation_challenges_invitation_id", "confirmation_challenges", ["invitation_id"])
    op.create_table("confirmation_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agreement_id", sa.String(36), sa.ForeignKey("agreements.id"), nullable=False),
        sa.Column("agreement_version_id", sa.String(36), sa.ForeignKey("agreement_versions.id"), nullable=False),
        sa.Column("invitation_id", sa.String(36), sa.ForeignKey("agreement_invitations.id"), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("verification_method", sa.String(32), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_confirmation_events_agreement_id", "confirmation_events", ["agreement_id"])
    op.create_table("audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("agreement_id", sa.String(36), sa.ForeignKey("agreements.id"), nullable=False),
        sa.Column("agreement_version_id", sa.String(36), sa.ForeignKey("agreement_versions.id")),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_business_id", "audit_events", ["business_id"])
    op.create_index("ix_audit_events_agreement_id", "audit_events", ["agreement_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("confirmation_events")
    op.drop_table("confirmation_challenges")
    op.drop_table("agreement_invitations")
    op.drop_table("agreement_versions")
    op.drop_table("agreements")
    op.drop_column("business_memberships", "can_manage_agreements")
