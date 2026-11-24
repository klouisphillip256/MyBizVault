import axios from 'axios'
import type { AgreementDetail, AgreementSummary, Counterparty, CurrentUser, DocumentCategory, DocumentDetail, DocumentSummary, ExternalProposalReview, ExternalReview, HealthResponse, InvitationResult, NegotiationKind, NegotiationRecord, ObligationEvent, PaymentRecord, StaffMember, Transaction } from '../types/domain'

const api = axios.create({ baseURL: '/api', timeout: 10000, withCredentials: true })

api.interceptors.request.use(config => {
  if (config.method && !['get', 'head', 'options'].includes(config.method.toLowerCase())) {
    const csrf = document.cookie.split('; ').find(part => part.startsWith('mbv_csrf='))?.split('=')[1]
    if (csrf) config.headers.set('X-CSRF-Token', decodeURIComponent(csrf))
  }
  return config
})

export function apiError(error: unknown): string {
  if (error instanceof Error && !axios.isAxiosError(error)) return error.message
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map(item => item.msg).join('; ')
    if (!error.response) return 'Cannot reach the API. Check that the backend is running.'
  }
  return 'Something went wrong. Please try again.'
}

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>('/health')
  return data
}
export const getDeliveryCapabilities = async () => (await api.get<{ email: boolean; sms: boolean }>('/delivery/capabilities')).data

export const getMe = async () => (await api.get<CurrentUser>('/auth/me')).data
export const registerOwner = async (input: { full_name: string; email: string; password: string; business_name: string }) => (await api.post<CurrentUser>('/auth/register', input)).data
export const login = async (input: { email: string; password: string }) => (await api.post<CurrentUser>('/auth/login', input)).data
export const logout = async () => { await api.post('/auth/logout') }
export const getCustomers = async (businessId: string) => (await api.get<Counterparty[]>(`/businesses/${businessId}/customers`)).data
export const createCustomer = async (businessId: string, input: { display_name: string; phone?: string; email?: string; notes?: string }) => (await api.post<Counterparty>(`/businesses/${businessId}/customers`, input)).data
export const updateCustomer = async (businessId: string, customerId: string, input: { display_name: string; phone?: string; email?: string; notes?: string }) => (await api.put<Counterparty>(`/businesses/${businessId}/customers/${customerId}`, input)).data
export const getTransactions = async (businessId: string) => (await api.get<Transaction[]>(`/businesses/${businessId}/transactions`)).data
export const createTransaction = async (businessId: string, input: { counterparty_id: string; client_request_id?: string; description: string; transaction_date: string; total_ugx: number; paid_ugx: number; due_date: string | null; delivery_notes?: string }) => (await api.post<Transaction>(`/businesses/${businessId}/transactions`, input)).data
export const getStaff = async (businessId: string) => (await api.get<StaffMember[]>(`/businesses/${businessId}/staff`)).data
export const createStaff = async (businessId: string, input: { full_name: string; email: string; password: string; can_view_transactions: boolean; can_create_transactions: boolean; can_manage_customers: boolean; can_manage_agreements: boolean; can_view_documents: boolean; can_manage_documents: boolean; can_manage_obligations: boolean }) => (await api.post<StaffMember>(`/businesses/${businessId}/staff`, input)).data
export const updateStaff = async (businessId: string, staffId: string, input: Pick<StaffMember, 'can_view_transactions' | 'can_create_transactions' | 'can_manage_customers' | 'can_manage_agreements' | 'can_view_documents' | 'can_manage_documents' | 'can_manage_obligations' | 'is_active'>) => (await api.patch<StaffMember>(`/businesses/${businessId}/staff/${staffId}`, input)).data
export const updateBusiness = async (businessId: string, name: string) => (await api.patch(`/businesses/${businessId}`, { name })).data
export const getAgreements = async (businessId: string) => (await api.get<AgreementSummary[]>(`/businesses/${businessId}/agreements`)).data
export const getAgreement = async (businessId: string, agreementId: string) => (await api.get<AgreementDetail>(`/businesses/${businessId}/agreements/${agreementId}`)).data
export const createAgreement = async (businessId: string, transactionId: string) => (await api.post<AgreementDetail>(`/businesses/${businessId}/agreements`, { transaction_id: transactionId })).data
export const reviseAgreement = async (businessId: string, agreementId: string, content: string) => (await api.put<AgreementDetail>(`/businesses/${businessId}/agreements/${agreementId}/draft`, { content })).data
export const createInvitation = async (businessId: string, agreementId: string) => (await api.post<InvitationResult>(`/businesses/${businessId}/agreements/${agreementId}/invitation`)).data
export const sendAgreementInvitation = async (businessId: string, agreementId: string, channel: 'email' | 'sms') => (await api.post<InvitationResult & { delivery_error?: string }>(`/businesses/${businessId}/agreements/${agreementId}/invitation/send`, { channel })).data
const invitationHeaders = (token: string) => ({ 'X-Invitation-Token': token })
export const getExternalReview = async (token: string) => (await api.get<ExternalReview>('/external/review', { headers: invitationHeaders(token) })).data
export const requestDevelopmentCode = async (token: string) => (await api.post<{ development_code: string; expires_at: string; warning: string }>('/external/challenge', {}, { headers: invitationHeaders(token) })).data
export const acceptExternalAgreement = async (token: string, versionId: string, code: string) => (await api.post<{ status: string; version_id: string }>('/external/accept', { version_id: versionId, code, explicitly_accepted: true }, { headers: invitationHeaders(token) })).data
export const respondExternalAgreement = async (token: string, versionId: string, action: 'rejected' | 'correction_requested', note: string) => (await api.post<{ status: string }>('/external/respond', { version_id: versionId, action, note }, { headers: invitationHeaders(token) })).data
export const listDocuments = async (businessId: string, q: string, category: string) => (await api.get<DocumentSummary[]>(`/businesses/${businessId}/documents`, { params: { q: q || undefined, category: category || undefined } })).data
export const getDocument = async (businessId: string, documentId: string) => (await api.get<DocumentDetail>(`/businesses/${businessId}/documents/${documentId}`)).data
export const uploadDocument = async (businessId: string, title: string, category: Exclude<DocumentCategory, 'agreement'>, file: File) => {
  const form = new FormData(); form.set('title', title); form.set('category', category); form.set('file', file)
  return (await api.post<DocumentDetail>(`/businesses/${businessId}/documents`, form)).data
}
export const uploadDocumentVersion = async (businessId: string, documentId: string, file: File) => {
  const form = new FormData(); form.set('file', file)
  return (await api.post<DocumentDetail>(`/businesses/${businessId}/documents/${documentId}/versions`, form)).data
}
export const getDocumentBlob = async (businessId: string, documentId: string, version: number, download = false) => (await api.get<Blob>(`/businesses/${businessId}/documents/${documentId}/versions/${version}/content`, { responseType: 'blob', params: { download } })).data
export const archiveAgreement = async (businessId: string, agreementId: string) => (await api.post<DocumentDetail>(`/businesses/${businessId}/agreements/${agreementId}/vault-document`)).data

const obligationPath = (businessId: string, transactionId: string) => `/businesses/${businessId}/transactions/${transactionId}`
export const getPayments = async (businessId: string, transactionId: string) => (await api.get<PaymentRecord[]>(`${obligationPath(businessId, transactionId)}/payments`)).data
export const createPayment = async (businessId: string, transactionId: string, input: { amount_ugx: number; paid_on: string; reference?: string; note?: string; evidence_document_id?: string | null }) => (await api.post<PaymentRecord>(`${obligationPath(businessId, transactionId)}/payments`, input)).data
export const setPaymentStatus = async (businessId: string, transactionId: string, paymentId: string, action: 'acknowledged' | 'disputed', note: string) => (await api.post<PaymentRecord>(`${obligationPath(businessId, transactionId)}/payments/${paymentId}/status`, { action, note })).data
export const getNegotiations = async (businessId: string, transactionId: string) => (await api.get<NegotiationRecord[]>(`${obligationPath(businessId, transactionId)}/negotiations`)).data
export const createNegotiation = async (businessId: string, transactionId: string, input: { kind: NegotiationKind; proposal: string; proposed_due_date?: string | null; proposed_amount_ugx?: number | null; evidence_document_id?: string | null }) => (await api.post<NegotiationRecord>(`${obligationPath(businessId, transactionId)}/negotiations`, input)).data
export const respondNegotiation = async (businessId: string, transactionId: string, negotiationId: string, action: 'accepted' | 'declined' | 'withdrawn' | 'resolved', note: string) => (await api.post<NegotiationRecord>(`${obligationPath(businessId, transactionId)}/negotiations/${negotiationId}/response`, { action, note })).data
export const getObligationHistory = async (businessId: string, transactionId: string) => (await api.get<ObligationEvent[]>(`${obligationPath(businessId, transactionId)}/obligation-history`)).data
export const createProposalInvitation = async (businessId: string, transactionId: string, proposalId: string) => (await api.post<{ review_url: string; expires_at: string; proposal_id: string; delivery: 'manual'; identity_verified: false }>(`${obligationPath(businessId, transactionId)}/negotiations/${proposalId}/invitation`)).data
export const sendProposalInvitation = async (businessId: string, transactionId: string, proposalId: string, channel: 'email' | 'sms') => (await api.post<{ review_url: string; expires_at: string; proposal_id: string; delivery: 'email' | 'sms' | 'failed'; delivery_error?: string }>(`${obligationPath(businessId, transactionId)}/negotiations/${proposalId}/invitation/send`, { channel })).data
export const getExternalProposal = async (token: string) => (await api.get<ExternalProposalReview>('/external/proposal', { headers: invitationHeaders(token) })).data
export const requestProposalCode = async (token: string) => (await api.post<{ development_code: string; expires_at: string; warning: string }>('/external/proposal/challenge', {}, { headers: invitationHeaders(token) })).data
export const respondExternalProposal = async (token: string, input: { proposal_id: string; action: 'accepted' | 'declined' | 'correction_requested'; note?: string; code?: string; explicitly_accepted?: boolean }) => (await api.post<{ status: string; proposal_id: string; identity_verified: false }>('/external/proposal/respond', input, { headers: invitationHeaders(token) })).data
