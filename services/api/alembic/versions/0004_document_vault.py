"""Private document metadata, immutable versions, and staff access.

Revision ID: 0004_document_vault
Revises: 0003_agreement_lifecycle
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_document_vault"
down_revision = "0003_agreement_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("business_memberships", sa.Column("can_view_documents", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("business_memberships", sa.Column("can_manage_documents", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("agreement_version_id", sa.String(36), sa.ForeignKey("agreement_versions.id"), unique=True),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_business_id", "documents", ["business_id"])
    op.create_index("ix_documents_business_category", "documents", ["business_id", "category"])
    op.create_table("document_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(300), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("filename", sa.String(180), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", "version", name="uq_document_version"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
    op.create_table("document_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("document_version_id", sa.String(36), sa.ForeignKey("document_versions.id"), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_events_business_id", "document_events", ["business_id"])
    op.create_index("ix_document_events_document_id", "document_events", ["document_id"])


def downgrade() -> None:
    op.drop_table("document_events")
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_column("business_memberships", "can_manage_documents")
    op.drop_column("business_memberships", "can_view_documents")
