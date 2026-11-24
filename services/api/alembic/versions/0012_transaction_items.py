"""Optional itemized sale facts; older transactions retain their description.

Revision ID: 0012_transaction_items
Revises: 0011_ussd_approval
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_transaction_items"
down_revision = "0011_ussd_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("line_items_json", sa.Text()))


def downgrade() -> None:
    op.drop_column("transactions", "line_items_json")
