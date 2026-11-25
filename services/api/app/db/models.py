from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Business(Base):
    __tablename__ = "businesses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Membership(Base):
    __tablename__ = "business_memberships"
    __table_args__ = (UniqueConstraint("business_id", "user_id", name="uq_membership_business_user"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(12))
    can_view_transactions: Mapped[bool] = mapped_column(Boolean, default=False)
    can_create_transactions: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_customers: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_agreements: Mapped[bool] = mapped_column(Boolean, default=False)
    can_view_documents: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_documents: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_obligations: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Session(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Counterparty(Base):
    __tablename__ = "counterparties"
    __table_args__ = (Index("ix_counterparties_business_name", "business_id", "display_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("total_ugx > 0", name="ck_transaction_total_positive"),
        CheckConstraint("paid_ugx >= 0 AND paid_ugx <= total_ugx", name="ck_transaction_paid_range"),
        Index("ix_transactions_business_date", "business_id", "transaction_date"),
        UniqueConstraint("business_id", "client_request_id", name="uq_transaction_client_request"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    counterparty_id: Mapped[str] = mapped_column(ForeignKey("counterparties.id"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    client_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    description: Mapped[str] = mapped_column(String(500))
    line_items_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    transaction_date: Mapped[date] = mapped_column(Date)
    total_ugx: Mapped[int] = mapped_column(Integer)
    paid_ugx: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Agreement(Base):
    __tablename__ = "agreements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24))
    current_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgreementVersion(Base):
    __tablename__ = "agreement_versions"
    __table_args__ = (UniqueConstraint("agreement_id", "version", name="uq_agreement_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agreement_id: Mapped[str] = mapped_column(ForeignKey("agreements.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgreementInvitation(Base):
    __tablename__ = "agreement_invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agreement_id: Mapped[str] = mapped_column(ForeignKey("agreements.id"), index=True)
    agreement_version_id: Mapped[str] = mapped_column(ForeignKey("agreement_versions.id"))
    counterparty_id: Mapped[str] = mapped_column(ForeignKey("counterparties.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_challenge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConfirmationChallenge(Base):
    __tablename__ = "confirmation_challenges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    invitation_id: Mapped[str] = mapped_column(ForeignKey("agreement_invitations.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(200))
    delivery_channel: Mapped[str | None] = mapped_column(String(24), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConfirmationEvent(Base):
    __tablename__ = "confirmation_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agreement_id: Mapped[str] = mapped_column(ForeignKey("agreements.id"), index=True)
    agreement_version_id: Mapped[str] = mapped_column(ForeignKey("agreement_versions.id"))
    invitation_id: Mapped[str] = mapped_column(ForeignKey("agreement_invitations.id"))
    counterparty_id: Mapped[str | None] = mapped_column(ForeignKey("counterparties.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(24))
    verification_method: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UssdApproval(Base):
    __tablename__ = "ussd_approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    invitation_id: Mapped[str] = mapped_column(ForeignKey("agreement_invitations.id"), unique=True)
    reference: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    code_hash: Mapped[str] = mapped_column(String(200))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    agreement_id: Mapped[str] = mapped_column(ForeignKey("agreements.id"), index=True)
    agreement_version_id: Mapped[str | None] = mapped_column(ForeignKey("agreement_versions.id"), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_business_category", "business_id", "category"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    category: Mapped[str] = mapped_column(String(24))
    source: Mapped[str] = mapped_column(String(24))
    agreement_version_id: Mapped[str | None] = mapped_column(ForeignKey("agreement_versions.id"), unique=True, nullable=True)
    current_version: Mapped[int] = mapped_column(Integer)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_document_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(80))
    filename: Mapped[str] = mapped_column(String(180))
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentEvent(Base):
    __tablename__ = "document_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id"))
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StoredObject(Base):
    """Private document bytes for serverless deployments without a bucket."""
    __tablename__ = "stored_objects"
    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(80))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaymentRecord(Base):
    __tablename__ = "payment_records"
    __table_args__ = (CheckConstraint("amount_ugx > 0", name="ck_payment_amount_positive"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    amount_ugx: Mapped[int] = mapped_column(Integer)
    paid_on: Mapped[date] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="reported")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Receipt(Base):
    """Immutable facts captured when a payment is first reported."""
    __tablename__ = "receipts"
    __table_args__ = (
        UniqueConstraint("payment_id", name="uq_receipt_payment"),
        Index("uq_receipt_initial_transaction", "transaction_id", unique=True,
              postgresql_where=text("kind = 'initial'"), sqlite_where=text("kind = 'initial'")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    payment_id: Mapped[str | None] = mapped_column(ForeignKey("payment_records.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(24))
    snapshot_json: Mapped[str] = mapped_column(Text)
    snapshot_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommunicationLog(Base):
    __tablename__ = "communication_logs"
    __table_args__ = (Index("ix_communication_logs_business_transaction", "business_id", "transaction_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"))
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"))
    agreement_id: Mapped[str | None] = mapped_column(ForeignKey("agreements.id"), nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(ForeignKey("negotiation_records.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(24))
    provider: Mapped[str] = mapped_column(String(32))
    provider_message_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    recipient_masked: Mapped[str] = mapped_column(String(254))
    status: Mapped[str] = mapped_column(String(24))
    detail: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NegotiationRecord(Base):
    __tablename__ = "negotiation_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    proposal: Mapped[str] = mapped_column(Text)
    proposed_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    proposed_amount_ugx: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="open")
    response_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ObligationEvent(Base):
    __tablename__ = "obligation_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    payment_id: Mapped[str | None] = mapped_column(ForeignKey("payment_records.id"), nullable=True)
    negotiation_id: Mapped[str | None] = mapped_column(ForeignKey("negotiation_records.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProposalInvitation(Base):
    __tablename__ = "proposal_invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    negotiation_id: Mapped[str] = mapped_column(ForeignKey("negotiation_records.id"), index=True)
    counterparty_id: Mapped[str] = mapped_column(ForeignKey("counterparties.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_challenge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProposalChallenge(Base):
    __tablename__ = "proposal_challenges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    invitation_id: Mapped[str] = mapped_column(ForeignKey("proposal_invitations.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(200))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProposalResponse(Base):
    __tablename__ = "proposal_responses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    negotiation_id: Mapped[str] = mapped_column(ForeignKey("negotiation_records.id"), index=True)
    invitation_id: Mapped[str] = mapped_column(ForeignKey("proposal_invitations.id"))
    action: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_method: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConsultationRequest(Base):
    """Private request draft; demonstration lawyer profiles receive no data."""
    __tablename__ = "consultation_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    profile_id: Mapped[str] = mapped_column(String(40))
    issue_type: Mapped[str] = mapped_column(String(40))
    issue_summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
