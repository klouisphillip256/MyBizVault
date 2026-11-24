"""Secure invitation lifecycle for individual negotiation proposals.

Revision ID: 0007_proposal_invitations
Revises: 0006_offline_request_ids
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_proposal_invitations"
down_revision = "0006_offline_request_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("negotiation_records", sa.Column("response_source", sa.String(32), nullable=True))
    op.create_table("proposal_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("negotiation_id", sa.String(36), sa.ForeignKey("negotiation_records.id"), nullable=False),
        sa.Column("counterparty_id", sa.String(36), sa.ForeignKey("counterparties.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_challenge_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_proposal_invitations_negotiation_id", "proposal_invitations", ["negotiation_id"])
    op.create_index("ix_proposal_invitations_token_hash", "proposal_invitations", ["token_hash"], unique=True)
    op.create_table("proposal_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invitation_id", sa.String(36), sa.ForeignKey("proposal_invitations.id"), nullable=False),
        sa.Column("code_hash", sa.String(200), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_proposal_challenges_invitation_id", "proposal_challenges", ["invitation_id"])
    op.create_table("proposal_responses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("negotiation_id", sa.String(36), sa.ForeignKey("negotiation_records.id"), nullable=False),
        sa.Column("invitation_id", sa.String(36), sa.ForeignKey("proposal_invitations.id"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("verification_method", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_proposal_responses_negotiation_id", "proposal_responses", ["negotiation_id"])


def downgrade() -> None:
    op.drop_table("proposal_responses")
    op.drop_table("proposal_challenges")
    op.drop_table("proposal_invitations")
    op.drop_column("negotiation_records", "response_source")
