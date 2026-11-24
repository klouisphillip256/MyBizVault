"""Idempotent transaction creation for retried offline drafts.

Revision ID: 0006_offline_request_ids
Revises: 0005_obligations_negotiation
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_offline_request_ids"
down_revision = "0005_obligations_negotiation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("client_request_id", sa.String(36), nullable=True))
    with op.batch_alter_table("transactions") as batch:
        batch.create_unique_constraint("uq_transaction_client_request", ["business_id", "client_request_id"])


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint("uq_transaction_client_request", type_="unique")
    op.drop_column("transactions", "client_request_id")
