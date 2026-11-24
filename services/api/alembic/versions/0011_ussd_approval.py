"""Bind sandbox USSD codes to immutable agreement versions and customers.

Revision ID: 0011_ussd_approval
Revises: 0010_communication_logs
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_ussd_approval"
down_revision = "0010_communication_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("confirmation_events")}
    if "counterparty_id" not in columns:
        op.add_column("confirmation_events", sa.Column("counterparty_id", sa.String(36)))
    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys("confirmation_events")
    if not any(item["constrained_columns"] == ["counterparty_id"] for item in foreign_keys):
        with op.batch_alter_table("confirmation_events") as batch:
            batch.create_foreign_key("fk_confirmation_events_counterparty", "counterparties",
                ["counterparty_id"], ["id"])
    op.create_table("ussd_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invitation_id", sa.String(36), sa.ForeignKey("agreement_invitations.id"),
                  nullable=False, unique=True),
        sa.Column("reference", sa.String(12), nullable=False),
        sa.Column("code_hash", sa.String(200), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_ussd_approvals_reference", "ussd_approvals", ["reference"], unique=True)


def downgrade() -> None:
    op.drop_table("ussd_approvals")
    with op.batch_alter_table("confirmation_events") as batch:
        batch.drop_constraint("fk_confirmation_events_counterparty", type_="foreignkey")
        batch.drop_column("counterparty_id")
