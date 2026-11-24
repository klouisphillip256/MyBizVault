"""Track how an agreement acceptance code was provided.

Revision ID: 0013_challenge_delivery
Revises: 0012_transaction_items
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_challenge_delivery"
down_revision = "0012_transaction_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("confirmation_challenges", sa.Column("delivery_channel", sa.String(24)))


def downgrade() -> None:
    op.drop_column("confirmation_challenges", "delivery_channel")
