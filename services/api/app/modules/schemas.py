from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    business_name: str = Field(min_length=2, max_length=160)

    @field_validator("full_name", "business_name", mode="before")
    @classmethod
    def trim_names(cls, value):
        return value.strip() if isinstance(value, str) else value


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class BusinessUpdateIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class StaffCreateIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    can_view_transactions: bool = False
    can_create_transactions: bool = False
    can_manage_customers: bool = False
    can_manage_agreements: bool = False
    can_view_documents: bool = False
    can_manage_documents: bool = False
    can_manage_obligations: bool = False

    @field_validator("full_name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class StaffUpdateIn(BaseModel):
    can_view_transactions: bool
    can_create_transactions: bool
    can_manage_customers: bool
    can_manage_agreements: bool = False
    can_view_documents: bool = False
    can_manage_documents: bool = False
    can_manage_obligations: bool = False
    is_active: bool


class CounterpartyIn(BaseModel):
    display_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("display_name", "phone", "notes", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def contact_required(self):
        if not self.phone and not self.email:
            raise ValueError("Provide a phone number or email address")
        return self


class TransactionLineIn(BaseModel):
    description: str = Field(min_length=2, max_length=180)
    quantity: int = Field(gt=0, le=100_000)
    unit_price_ugx: int = Field(gt=0, le=1_000_000_000_000)

    @field_validator("description", mode="before")
    @classmethod
    def trim_description(cls, value):
        return value.strip() if isinstance(value, str) else value


class TransactionIn(BaseModel):
    counterparty_id: str
    client_request_id: UUID | None = None
    description: str = Field(min_length=3, max_length=500)
    line_items: list[TransactionLineIn] = Field(default_factory=list, max_length=30)
    transaction_date: date
    total_ugx: int = Field(gt=0, le=1_000_000_000_000)
    paid_ugx: int = Field(ge=0, le=1_000_000_000_000)
    due_date: date | None = None
    delivery_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("description", "delivery_notes", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def valid_amounts_and_dates(self):
        if self.paid_ugx > self.total_ugx:
            raise ValueError("Amount paid cannot exceed total value")
        if self.paid_ugx < self.total_ugx and self.due_date is None:
            raise ValueError("A payment deadline is required when a balance remains")
        if self.due_date and self.due_date < self.transaction_date:
            raise ValueError("Payment deadline cannot precede transaction date")
        if self.line_items and sum(item.quantity * item.unit_price_ugx for item in self.line_items) != self.total_ugx:
            raise ValueError("Itemized amounts must equal the transaction total")
        return self


class AgreementDraftIn(BaseModel):
    content: str = Field(min_length=40, max_length=20000)

    @field_validator("content", mode="before")
    @classmethod
    def trim_content(cls, value):
        return value.strip() if isinstance(value, str) else value


class AgreementCreateIn(BaseModel):
    transaction_id: str


class ExternalResponseIn(BaseModel):
    version_id: str
    action: str
    note: str | None = Field(default=None, max_length=2000)


class AgreementAcceptIn(BaseModel):
    version_id: str
    code: str = Field(pattern=r"^[0-9]{6}$")
    explicitly_accepted: bool


class PaymentRecordIn(BaseModel):
    amount_ugx: int = Field(gt=0, le=1_000_000_000_000)
    paid_on: date
    reference: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=2000)
    evidence_document_id: str | None = None


class PaymentStatusIn(BaseModel):
    action: Literal["acknowledged", "disputed"]
    note: str = Field(min_length=3, max_length=2000)


class NegotiationIn(BaseModel):
    kind: Literal["extension", "instalment_plan", "contract_correction", "settlement", "revised_obligation", "payment_dispute"]
    proposal: str = Field(min_length=10, max_length=5000)
    proposed_due_date: date | None = None
    proposed_amount_ugx: int | None = Field(default=None, gt=0, le=1_000_000_000_000)
    evidence_document_id: str | None = None


class NegotiationResponseIn(BaseModel):
    action: Literal["accepted", "declined", "withdrawn", "resolved"]
    note: str = Field(min_length=3, max_length=2000)


class ExternalProposalResponseIn(BaseModel):
    proposal_id: str
    action: Literal["accepted", "declined", "correction_requested"]
    note: str | None = Field(default=None, max_length=2000)
    code: str | None = Field(default=None, pattern=r"^[0-9]{6}$")
    explicitly_accepted: bool = False


class SendInvitationIn(BaseModel):
    channel: Literal["email", "sms", "whatsapp"]
