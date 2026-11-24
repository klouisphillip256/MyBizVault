import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDownLeft, CalendarClock, FileText, Handshake, MessageSquareText, Plus, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../components/ui/button'
import { apiError, createNegotiation, createPayment, createProposalInvitation, getDeliveryCapabilities, getNegotiations, getObligationHistory, getPayments, getTransactions, listDocuments, respondNegotiation, sendProposalInvitation, setPaymentStatus } from '../lib/api'
import { ugx } from '../lib/utils'
import type { Membership, NegotiationKind, NegotiationRecord, PaymentRecord, Transaction } from '../types/domain'

type Mode = 'payments' | 'negotiations' | 'disputes'
const proposalLabels: Record<NegotiationKind, string> = {
  extension: 'Payment extension', instalment_plan: 'Instalment plan', contract_correction: 'Contract correction',
  settlement: 'Settlement', revised_obligation: 'Revised obligation', payment_dispute: 'Payment dispute',
}
const today = () => new Date().toISOString().slice(0, 10)
const note = 'These entries are recorded by your business. They do not prove payment or customer agreement.'

function ErrorMessage({ error }: { error: unknown }) { return <div role="alert" className="form-error">{apiError(error)}</div> }

function PaymentPanel({ businessId, transaction, canManage, canViewDocuments }: { businessId: string; transaction: Transaction; canManage: boolean; canViewDocuments: boolean }) {
  const queryClient = useQueryClient()
  const [amount, setAmount] = useState('')
  const [paidOn, setPaidOn] = useState(today())
  const [reference, setReference] = useState('')
  const [paymentNote, setPaymentNote] = useState('')
  const [evidence, setEvidence] = useState('')
  const [statusNote, setStatusNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const { data: payments = [], isPending } = useQuery({ queryKey: ['payments', businessId, transaction.id], queryFn: () => getPayments(businessId, transaction.id) })
  const { data: documents = [] } = useQuery({ queryKey: ['documents', businessId, '', ''], queryFn: () => listDocuments(businessId, '', ''), enabled: canViewDocuments })
  const refresh = async () => { await Promise.all([queryClient.invalidateQueries({ queryKey: ['payments', businessId, transaction.id] }), queryClient.invalidateQueries({ queryKey: ['transactions', businessId] }), queryClient.invalidateQueries({ queryKey: ['obligation-history', businessId, transaction.id] })]) }
  const save = async () => {
    const value = Number(amount)
    if (!Number.isSafeInteger(value) || value <= 0 || value > transaction.balance_ugx) { setError(new Error('Enter an amount within the outstanding balance.')); return }
    setBusy(true); setError(null)
    try { await createPayment(businessId, transaction.id, { amount_ugx: value, paid_on: paidOn, reference, note: paymentNote, evidence_document_id: evidence || null }); setAmount(''); setReference(''); setPaymentNote(''); setEvidence(''); await refresh() }
    catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  const change = async (item: PaymentRecord, action: 'acknowledged' | 'disputed') => {
    if (statusNote.trim().length < 3) { setError(new Error('Add a reason or acknowledgment note.')); return }
    setBusy(true); setError(null)
    try { await setPaymentStatus(businessId, transaction.id, item.id, action, statusNote.trim()); setStatusNote(''); await refresh() }
    catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  return <><div className="obligation-metrics"><div><span>Original value</span><strong>{ugx(transaction.total_ugx)}</strong></div><div><span>Initial reported paid</span><strong>{ugx(transaction.paid_ugx)}</strong></div><div><span>Later reported paid</span><strong>{ugx(transaction.additional_paid_ugx)}</strong></div><div><span>Disputed</span><strong>{ugx(transaction.disputed_ugx)}</strong></div><div><span>Outstanding</span><strong>{ugx(transaction.balance_ugx)}</strong></div></div><p className="obligation-caution"><ShieldCheck size={17} /> {note}</p>{!transaction.balance_ugx && Boolean(error) && <ErrorMessage error={error} />}{canManage && transaction.balance_ugx > 0 && <div className="card form-card form-stack"><h3>Record a payment</h3><div className="field-grid"><label>Amount (UGX)<input type="number" min="1" max={transaction.balance_ugx} step="1" value={amount} onChange={event => setAmount(event.target.value)} /></label><label>Payment date<input type="date" min={transaction.transaction_date} max={today()} value={paidOn} onChange={event => setPaidOn(event.target.value)} /></label></div><label>Reference (optional)<input value={reference} onChange={event => setReference(event.target.value)} maxLength={120} /></label><label>Note (optional)<textarea value={paymentNote} onChange={event => setPaymentNote(event.target.value)} maxLength={2000} rows={2} /></label>{canViewDocuments && <label>Supporting Vault document (optional)<select value={evidence} onChange={event => setEvidence(event.target.value)}><option value="">None</option>{documents.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>}{Boolean(error) && <ErrorMessage error={error} />}<Button onClick={save} disabled={busy || !amount}><Plus size={16} /> Record payment</Button></div>}<div className="card module-card"><h3>Payment history</h3>{isPending ? <p className="field-hint">Loading payments…</p> : payments.length === 0 ? <p className="field-hint">No later payments recorded.</p> : payments.map(item => <div className="obligation-entry" key={item.id}><div><strong>{ugx(item.amount_ugx)}</strong><small>{item.paid_on} · {item.status.replaceAll('_', ' ')} · business recorded</small>{item.reference && <p>Reference: {item.reference}</p>}{item.note && <p>{item.note}</p>}{item.evidence_document_id && canViewDocuments && <Link className="text-link" to={`/vault?document=${item.evidence_document_id}`}><FileText size={14} /> View evidence</Link>}</div>{canManage && <div className="obligation-actions"><input value={statusNote} onChange={event => setStatusNote(event.target.value)} placeholder="Reason or acknowledgment note" maxLength={2000} aria-label="Payment status note" />{item.status !== 'acknowledged' && <Button size="small" variant="outline" disabled={busy} onClick={() => change(item, 'acknowledged')}>Business acknowledges</Button>}{item.status !== 'disputed' && <Button size="small" variant="outline" disabled={busy} onClick={() => change(item, 'disputed')}>Mark disputed</Button>}</div>}</div>)}</div></>
}

function NegotiationPanel({ businessId, transaction, mode, canManage, canViewDocuments }: { businessId: string; transaction: Transaction; mode: 'negotiations' | 'disputes'; canManage: boolean; canViewDocuments: boolean }) {
  const queryClient = useQueryClient()
  const [kind, setKind] = useState<NegotiationKind>(mode === 'disputes' ? 'payment_dispute' : 'extension')
  const [proposal, setProposal] = useState('')
  const [proposedDate, setProposedDate] = useState('')
  const [proposedAmount, setProposedAmount] = useState('')
  const [evidence, setEvidence] = useState('')
  const [responseNote, setResponseNote] = useState('')
  const [reviewLink, setReviewLink] = useState<{ id: string; url: string } | null>(null)
  const [deliveryStatus, setDeliveryStatus] = useState('')
  const { data: delivery } = useQuery({ queryKey: ['delivery-capabilities'], queryFn: getDeliveryCapabilities })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const { data: all = [], isPending } = useQuery({ queryKey: ['negotiations', businessId, transaction.id], queryFn: () => getNegotiations(businessId, transaction.id) })
  const { data: documents = [] } = useQuery({ queryKey: ['documents', businessId, '', ''], queryFn: () => listDocuments(businessId, '', ''), enabled: canViewDocuments })
  const items = all.filter(item => mode === 'disputes' ? item.kind === 'payment_dispute' : item.kind !== 'payment_dispute')
  const refresh = async () => { await Promise.all([queryClient.invalidateQueries({ queryKey: ['negotiations', businessId, transaction.id] }), queryClient.invalidateQueries({ queryKey: ['transactions', businessId] }), queryClient.invalidateQueries({ queryKey: ['obligation-history', businessId, transaction.id] })]) }
  const save = async () => {
    if (proposal.trim().length < 10) { setError(new Error('Describe the request in at least ten characters.')); return }
    setBusy(true); setError(null)
    try { await createNegotiation(businessId, transaction.id, { kind: mode === 'disputes' ? 'payment_dispute' : kind, proposal: proposal.trim(), proposed_due_date: proposedDate || null, proposed_amount_ugx: proposedAmount ? Number(proposedAmount) : null, evidence_document_id: evidence || null }); setProposal(''); setProposedDate(''); setProposedAmount(''); setEvidence(''); await refresh() }
    catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  const respond = async (item: NegotiationRecord, action: 'accepted' | 'declined' | 'withdrawn' | 'resolved') => {
    if (responseNote.trim().length < 3) { setError(new Error('Add a response or resolution note.')); return }
    setBusy(true); setError(null)
    try { await respondNegotiation(businessId, transaction.id, item.id, action, responseNote.trim()); setResponseNote(''); await refresh() }
    catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  const invite = async (item: NegotiationRecord) => {
    setBusy(true); setError(null); setDeliveryStatus('')
    try { const result = await createProposalInvitation(businessId, transaction.id, item.id); setReviewLink({ id: item.id, url: result.review_url }) }
    catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  const send = async (item: NegotiationRecord, channel: 'email' | 'sms' | 'whatsapp') => {
    setBusy(true); setError(null); setDeliveryStatus('')
    try {
      const result = await sendProposalInvitation(businessId, transaction.id, item.id, channel)
      setReviewLink({ id: item.id, url: result.review_url })
      setDeliveryStatus(result.delivery === 'failed' ? `${channel.toUpperCase()} submission failed. Share this link manually.` : `${channel.toUpperCase()} ${result.delivery_status || 'submitted'}; delivery is not confirmed.`)
    } catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  return <><p className="obligation-caution"><ShieldCheck size={17} /> {note} An accepted proposal may change the displayed working deadline; the original contract remains unchanged.</p>{canManage && <div className="card form-card form-stack"><h3>{mode === 'disputes' ? 'Open a dispute record' : 'Record a proposal'}</h3>{mode === 'negotiations' && <label>Proposal type<select value={kind} onChange={event => setKind(event.target.value as NegotiationKind)}>{Object.entries(proposalLabels).filter(([key]) => key !== 'payment_dispute').map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>}<label>Details<textarea value={proposal} onChange={event => setProposal(event.target.value)} rows={4} maxLength={5000} placeholder={mode === 'disputes' ? 'Describe the disagreement and requested resolution' : 'Describe the proposed change'} /></label>{mode === 'negotiations' && <div className="field-grid"><label>Proposed final due date<input type="date" value={proposedDate} onChange={event => setProposedDate(event.target.value)} /></label><label>Proposed amount (UGX)<input type="number" min="1" step="1" value={proposedAmount} onChange={event => setProposedAmount(event.target.value)} /></label></div>}{canViewDocuments && <label>Supporting Vault document (optional)<select value={evidence} onChange={event => setEvidence(event.target.value)}><option value="">None</option>{documents.map(item => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>}{Boolean(error) && <ErrorMessage error={error} />}<Button onClick={save} disabled={busy || proposal.trim().length < 10}><Plus size={16} /> Save record</Button></div>}<div className="card module-card"><h3>{mode === 'disputes' ? 'Dispute and resolution history' : 'Proposals and outcomes'}</h3>{isPending ? <p className="field-hint">Loading records…</p> : items.length === 0 ? <p className="field-hint">No records yet.</p> : items.map(item => <div className="obligation-entry" key={item.id}><div><strong>{proposalLabels[item.kind]} · {item.status}</strong><small>{new Date(item.created_at).toLocaleString()} · {item.verification_source.replaceAll('_', ' ')}</small><p>{item.proposal}</p>{item.proposed_due_date && <p>Proposed date: {item.proposed_due_date}</p>}{item.proposed_amount_ugx && <p>Proposed amount: {ugx(item.proposed_amount_ugx)}</p>}{item.evidence_document_id && canViewDocuments && <Link className="text-link" to={`/vault?document=${item.evidence_document_id}`}><FileText size={14} /> View evidence</Link>}</div>{canManage && item.status === 'open' && <div className="obligation-actions"><Button size="small" variant="outline" disabled={busy} onClick={() => invite(item)}>Create review link</Button>{delivery?.email && <Button size="small" variant="outline" disabled={busy} onClick={() => send(item, 'email')}>Send email link</Button>}{delivery?.sms && <Button size="small" variant="outline" disabled={busy} onClick={() => send(item, 'sms')}>Send SMS link</Button>}{delivery?.whatsapp && <Button size="small" variant="outline" disabled={busy} onClick={() => send(item, 'whatsapp')}>Send WhatsApp link</Button>}{reviewLink?.id === item.id && <div className="proposal-link"><p>{deliveryStatus || 'Share manually with the intended customer.'} Creating another link revokes this one.</p><input value={reviewLink.url} readOnly onFocus={event => event.target.select()} aria-label="Proposal review link" /><a className="text-link" href={`https://wa.me/?text=${encodeURIComponent(reviewLink.url)}`} target="_blank" rel="noopener noreferrer">Share in WhatsApp</a></div>}<input value={responseNote} onChange={event => setResponseNote(event.target.value)} placeholder="Response or resolution note" maxLength={2000} aria-label="Proposal response note" />{mode === 'disputes' ? <Button size="small" variant="outline" disabled={busy} onClick={() => respond(item, 'resolved')}>Record resolution</Button> : <><Button size="small" variant="outline" disabled={busy} onClick={() => respond(item, 'accepted')}>Record accepted</Button><Button size="small" variant="outline" disabled={busy} onClick={() => respond(item, 'declined')}>Record declined</Button></>}<Button size="small" variant="ghost" disabled={busy} onClick={() => respond(item, 'withdrawn')}>Withdraw</Button></div>}</div>)}</div></>
}

export function ObligationsPage({ membership, mode }: { membership: Membership; mode: Mode }) {
  const businessId = membership.business_id
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data: transactions = [], isPending, error } = useQuery({ queryKey: ['transactions', businessId], queryFn: () => getTransactions(businessId), enabled: membership.can_view_transactions })
  const selected = transactions.find(item => item.id === selectedId) || null
  const { data: history = [] } = useQuery({ queryKey: ['obligation-history', businessId, selectedId], queryFn: () => getObligationHistory(businessId, selectedId!), enabled: !!selected && membership.can_view_transactions })
  const title = mode === 'payments' ? 'Payments & obligations' : mode === 'negotiations' ? 'Negotiations' : 'Disputes'
  const Icon = mode === 'payments' ? ArrowDownLeft : mode === 'negotiations' ? Handshake : MessageSquareText
  return <><div className="section-intro"><div><p className="eyebrow">BUSINESS RECORDS</p><h1>{title}</h1><p>Track what your business has recorded against each transaction, with its original terms and history.</p></div></div>{!membership.can_view_transactions ? <div className="card module-card"><p>Transaction access not granted.</p></div> : <div className="obligation-layout"><div className="card module-card"><h3>Select a transaction</h3>{isPending ? <p className="field-hint">Loading transactions…</p> : error ? <ErrorMessage error={error} /> : transactions.length === 0 ? <p className="field-hint">Create a transaction first.</p> : <div className="obligation-list">{transactions.map(item => <button key={item.id} className={`obligation-list-item ${selectedId === item.id ? 'selected' : ''}`} onClick={() => setSelectedId(item.id)}><Icon size={18} /><span><strong>{item.counterparty_name}</strong><small>{ugx(item.balance_ugx)} outstanding · {item.is_overdue ? 'Overdue' : item.effective_due_date || 'Paid'}</small></span></button>)}</div>}</div><div className="obligation-detail">{selected ? <><div className="card module-card"><h2>{selected.counterparty_name}</h2><p>{selected.description}</p><div className="obligation-dates"><span><CalendarClock size={15} /> Original deadline: {selected.due_date || 'None'}</span><span>Working deadline: {selected.effective_due_date || 'None'}{selected.due_date_source === 'business_recorded_proposal' ? ' (business-recorded proposal)' : ''}</span></div>{selected.is_overdue && <strong className="obligation-overdue">Overdue based on the working deadline</strong>}</div>{mode === 'payments' ? <PaymentPanel businessId={businessId} transaction={selected} canManage={membership.can_manage_obligations} canViewDocuments={membership.can_view_documents} /> : <NegotiationPanel key={`${mode}-${selected.id}`} businessId={businessId} transaction={selected} mode={mode} canManage={membership.can_manage_obligations} canViewDocuments={membership.can_view_documents} />}<div className="card module-card"><h3>Activity log</h3>{history.length ? history.map(item => <div className="obligation-event" key={item.id}><strong>{item.action.replaceAll('_', ' ')}</strong><small>{new Date(item.created_at).toLocaleString()}</small>{item.note && <p>{item.note}</p>}</div>) : <p className="field-hint">No activity recorded yet.</p>}</div></> : <div className="card module-card"><div className="empty-state"><Icon size={28} /><h3>Choose a transaction</h3><p>Open its payment, negotiation and dispute records.</p></div></div>}</div></div>}</>
}
