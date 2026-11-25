"""Store private demonstration consultation requests.

Revision ID: 0015_consultation_requests
Revises: 0014_unique_initial_receipts
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_consultation_requests"
down_revision = "0014_unique_initial_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("consultation_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("requested_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("profile_id", sa.String(40), nullable=False),
        sa.Column("issue_type", sa.String(40), nullable=False),
        sa.Column("issue_summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_consultation_requests_business_id", "consultation_requests", ["business_id"])


def downgrade() -> None:
    op.drop_index("ix_consultation_requests_business_id", table_name="consultation_requests")
    op.drop_table("consultation_requests")
