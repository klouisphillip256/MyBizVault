export interface Membership {
  id: string
  business_id: string
  business_name: string
  business_phone: string | null
  business_email: string | null
  role: 'owner' | 'staff'
  can_view_transactions: boolean
  can_create_transactions: boolean
  can_manage_customers: boolean
  can_manage_agreements: boolean
  can_view_documents: boolean
  can_manage_documents: boolean
  can_manage_obligations: boolean
}

export interface CurrentUser {
  id: string
  full_name: string
  email: string
  memberships: Membership[]
}

export interface Counterparty {
  id: string
  display_name: string
  phone: string | null
  email: string | null
  notes: string | null
  created_at: string
}

export interface Transaction {
  id: string
  counterparty_id: string
  counterparty_name: string
  description: string
  line_items: { description: string; quantity: number; unit_price_ugx: number }[]
  transaction_date: string
  total_ugx: number
  paid_ugx: number
  balance_ugx: number
  additional_paid_ugx: number
  disputed_ugx: number
  effective_due_date: string | null
  due_date_source: 'original_transaction' | 'business_recorded_proposal'
  is_overdue: boolean
  due_date: string | null
  delivery_notes: string | null
  payment_record_status: 'reported'
  created_at: string
}

export interface ReceiptSummary {
  id: string
  transaction_id: string
  payment_id: string | null
  kind: 'initial' | 'payment'
  amount_ugx: number
  payment_date: string
  payment_status_at_issue: string
  created_at: string
  sha256: string
}

export interface TransactionDetail extends Transaction {
  customer_phone: string | null
  customer_email: string | null
  receipts: ReceiptSummary[]
  payments: PaymentRecord[]
  approval_history: ObligationEvent[]
  communications: { id: string; channel: string; provider: string; recipient_masked: string; status: string; detail: string | null; created_at: string; updated_at: string }[]
  agreement: { id: string; status: AgreementStatus; current_version: number } | null
}

export interface StaffMember {
  id: string
  full_name: string
  email: string
  can_view_transactions: boolean
  can_create_transactions: boolean
  can_manage_customers: boolean
  can_manage_agreements: boolean
  can_view_documents: boolean
  can_manage_documents: boolean
  can_manage_obligations: boolean
  is_active: boolean
}

export type DocumentCategory = 'contract' | 'receipt' | 'image' | 'other' | 'agreement'

export interface DocumentVersion {
  id: string
  version: number
  filename: string
  content_type: string
  size_bytes: number
  sha256: string
  created_at: string
}

export interface DocumentSummary {
  id: string
  title: string
  category: DocumentCategory
  source: 'upload' | 'agreement'
  agreement_version_id: string | null
  current_version: number
  created_at: string
  current_file: DocumentVersion
}

export interface DocumentDetail extends DocumentSummary {
  versions: DocumentVersion[]
  events: { action: string; version_id: string; created_at: string }[]
}

export type AgreementStatus = 'draft' | 'invited' | 'confirmed' | 'correction_requested' | 'rejected'

export interface AgreementSummary {
  id: string
  transaction_id: string
  counterparty_name: string
  status: AgreementStatus
  current_version: number
  current_version_id: string
  content_sha256: string
  balance_ugx: number
  created_at: string
}

export interface AgreementVersion {
  id: string
  version: number
  content: string
  content_sha256: string
  created_at: string
}

export interface AgreementEvent {
  action: string
  version_id: string
  verification_method: string
  note: string | null
  created_at: string
}

export interface AgreementDetail extends AgreementSummary {
  versions: AgreementVersion[]
  events: AgreementEvent[]
  audit: { action: string; detail: string | null; created_at: string }[]
}

export interface ExternalReview {
  agreement_id: string
  version_id: string
  version: number
  status: AgreementStatus
  content: string
  content_sha256: string
  business_name: string
  counterparty_name: string
  transaction_id: string
  total_ugx: number
  paid_ugx: number
  balance_ugx: number
  due_date: string
  development_verification: boolean
  verification_delivery_available: boolean
  identity_verified: false
  expires_at: string
}

export interface InvitationResult {
  review_url: string
  expires_at: string
  version_id: string
  delivery: 'manual' | 'email' | 'sms' | 'whatsapp' | 'failed'
  delivery_status?: 'simulated' | 'submitted' | 'delivered' | 'failed'
  delivery_error?: string
  identity_verified: false
}

export interface HealthResponse {
  status: 'ok'
  database: 'connected'
}

export interface PaymentRecord {
  id: string
  transaction_id: string
  amount_ugx: number
  paid_on: string
  reference: string | null
  note: string | null
  evidence_document_id: string | null
  status: 'reported' | 'acknowledged' | 'disputed'
  verification_source: 'business_recorded'
  created_at: string
}

export type NegotiationKind = 'extension' | 'instalment_plan' | 'contract_correction' | 'settlement' | 'revised_obligation' | 'payment_dispute'

export type LawyerProfile = { id: string; name: string; specialization: string; focus: string[]; location: string; consultation_method: string; availability: string; fictional: true }
export type ConsultationRequest = { id: string; profile_id: string; issue_type: string; issue_summary: string; status: 'draft'; created_at: string }
export interface NegotiationRecord {
  id: string
  transaction_id: string
  kind: NegotiationKind
  proposal: string
  proposed_due_date: string | null
  proposed_amount_ugx: number | null
  evidence_document_id: string | null
  status: 'open' | 'accepted' | 'declined' | 'withdrawn' | 'resolved' | 'correction_requested'
  verification_source: 'business_recorded' | 'development_code' | 'invitation_link_only'
  created_at: string
}

export interface ExternalProposalReview {
  proposal_id: string
  kind: NegotiationKind
  proposal: string
  proposed_due_date: string | null
  proposed_amount_ugx: number | null
  status: NegotiationRecord['status'] | 'correction_requested'
  business_name: string
  counterparty_name: string
  transaction_description: string
  original_due_date: string | null
  total_ugx: number
  initial_paid_ugx: number
  development_verification: boolean
  identity_verified: false
  expires_at: string
}

export interface ObligationEvent {
  id: string
  payment_id: string | null
  negotiation_id: string | null
  action: string
  note: string | null
  created_at: string
}
