import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpenCheck, CheckCircle2, ChevronRight, CircleAlert, ClipboardCopy, FileCheck2, History, LockKeyhole, Plus, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Button } from '../components/ui/button'
import { acceptExternalAgreement, apiError, archiveAgreement, createAgreement, createInvitation, getAgreement, getAgreements, getDeliveryCapabilities, getExternalReview, getTransactions, requestDevelopmentCode, respondExternalAgreement, reviseAgreement, sendAgreementInvitation, sendUssdApproval } from '../lib/api'
import { ugx } from '../lib/utils'
import type { AgreementDetail, AgreementStatus, Membership } from '../types/domain'

const labels: Record<AgreementStatus, string> = {
  draft: 'Draft', invited: 'Awaiting response', confirmed: 'Confirmed',
  correction_requested: 'Correction requested', rejected: 'Rejected',
}

function ErrorMessage({ error }: { error: unknown }) { return <div role="alert" className="form-error">{apiError(error)}</div> }

function AgreementEditor({ detail, businessId, canArchive, onChange }: { detail: AgreementDetail; businessId: string; canArchive: boolean; onChange: () => Promise<void> }) {
  const navigate = useNavigate()
  const current = detail.versions.find(item => item.version === detail.current_version)!
  const [content, setContent] = useState(current.content)
  const [reviewLink, setReviewLink] = useState<string | null>(null)
  const [linkExpiry, setLinkExpiry] = useState<string | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [copyStatus, setCopyStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [deliveryStatus, setDeliveryStatus] = useState('')
  const { data: delivery } = useQuery({ queryKey: ['delivery-capabilities'], queryFn: getDeliveryCapabilities })
  const save = async () => {
    setBusy(true); setError(null)
    try { await reviseAgreement(businessId, detail.id, content); setReviewLink(null); await onChange() }
    catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  const invite = async () => {
    setBusy(true); setError(null); setCopyStatus('')
    try { const result = await createInvitation(businessId, detail.id); setReviewLink(result.review_url); setLinkExpiry(result.expires_at); await onChange() }
    catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  const send = async (channel: 'email' | 'sms' | 'whatsapp') => {
    setBusy(true); setError(null); setCopyStatus(''); setDeliveryStatus('')
    try {
      const result = await sendAgreementInvitation(businessId, detail.id, channel)
      setReviewLink(result.review_url); setLinkExpiry(result.expires_at)
      setDeliveryStatus(result.delivery === 'failed' ? `${channel.toUpperCase()} submission failed. Share this link manually.` : `${channel.toUpperCase()} ${result.delivery_status || 'submitted'}; delivery is not confirmed.`)
      await onChange()
    } catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  const sendUssd = async () => {
    setBusy(true); setError(null); setDeliveryStatus('')
    try {
      const result = await sendUssdApproval(businessId, detail.id)
      setReviewLink(result.review_url); setLinkExpiry(result.expires_at || null)
      setDeliveryStatus(result.status === 'failed' ? result.error || 'Sandbox SMS failed.' : `USSD reference ${result.reference} ${result.status}. The customer must enter the SMS code and explicitly respond.`)
      await onChange()
    } catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  const copy = async () => {
    if (!reviewLink) return
    try { await navigator.clipboard.writeText(reviewLink); setCopyStatus('Copied to clipboard') }
    catch { setCopyStatus('Select and copy the link below') }
  }
  const openVaultCopy = async () => {
    setBusy(true); setError(null)
    try { const document = await archiveAgreement(businessId, detail.id); navigate(`/vault?document=${document.id}`) }
    catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  const canEdit = detail.status !== 'confirmed'
  return <div className="agreement-detail">
    <div className="agreement-title"><div><p className="eyebrow">{detail.counterparty_name.toUpperCase()}</p><h2>Credit sale agreement</h2><p>Version {detail.current_version} · {labels[detail.status]} · {ugx(detail.balance_ugx)} outstanding</p></div><span className={`agreement-status agreement-${detail.status}`}>{labels[detail.status]}</span></div>
    {detail.status === 'confirmed' && <div className="agreement-confirmed-note"><CheckCircle2 size={19} /><span>This exact version is preserved. New terms require a separately confirmed amendment.</span></div>}
    {detail.status === 'confirmed' && canArchive && <Button variant="outline" onClick={openVaultCopy} disabled={busy}>Open preserved copy in Vault</Button>}
    {detail.status === 'correction_requested' && <div className="agreement-guidance">The customer requested a correction. Edit the full draft below, save a new version, then create a new review link.</div>}
    {detail.status === 'rejected' && <div className="agreement-guidance">The customer rejected this version. Any revised proposal must be saved as a new version.</div>}
    <label className="agreement-editor-label">Full agreement terms<textarea value={content} onChange={event => setContent(event.target.value)} readOnly={!canEdit} rows={19} aria-label="Full agreement terms" /></label><p className="field-hint">The transaction facts above the Proposed terms heading are locked to the saved sale. Edit the proposed terms below; changing sale amounts or dates requires a new transaction record.</p>
    <div className="hash-line"><LockKeyhole size={14} /> SHA-256: <code>{current.content_sha256}</code></div>
    {Boolean(error) && <ErrorMessage error={error} />}
    <div className="agreement-actions">{canEdit && <Button onClick={save} disabled={busy || content.trim() === current.content || content.trim().length < 40}>Save new version</Button>}{['draft', 'invited'].includes(detail.status) && <Button variant="outline" onClick={invite} disabled={busy}>{detail.status === 'invited' ? 'Reissue review link' : 'Create review link'}</Button>}{['draft', 'invited'].includes(detail.status) && delivery?.email && <Button variant="outline" onClick={() => send('email')} disabled={busy}>Send email link</Button>}{['draft', 'invited'].includes(detail.status) && delivery?.sms && <Button variant="outline" onClick={() => send('sms')} disabled={busy}>Send SMS link</Button>}{['draft', 'invited'].includes(detail.status) && delivery?.whatsapp && <Button variant="outline" onClick={() => send('whatsapp')} disabled={busy}>Send WhatsApp link</Button>}{['draft', 'invited'].includes(detail.status) && delivery?.ussd && <Button variant="outline" onClick={sendUssd} disabled={busy}>Send USSD approval code</Button>}</div>
    {deliveryStatus && <p role="status" className="field-hint">{deliveryStatus}</p>}
    {detail.status === 'invited' && !reviewLink && <p className="field-hint">A review link exists. To get a new copy, reissue it; the previous link will stop working.</p>}
    {reviewLink && <div className="link-panel"><div><strong>Review link ready for manual sharing</strong><p>Share this with the intended customer through a channel you trust. {deliveryStatus ? 'Check the communication status above.' : 'No message has been sent by MyBizVault.'} Creating another link will revoke this one.</p></div><input value={reviewLink} readOnly aria-label="Customer review link" onFocus={event => event.target.select()} /><Button onClick={copy} variant="outline"><ClipboardCopy size={16} /> Copy link</Button><a className="text-link" href={`https://wa.me/?text=${encodeURIComponent(reviewLink)}`} target="_blank" rel="noopener noreferrer">Share in WhatsApp</a><small>{copyStatus || `Expires ${linkExpiry ? new Date(linkExpiry).toLocaleString() : 'in seven days'}`}</small></div>}
    <div className="agreement-history"><h3><History size={18} /> Version history</h3>{detail.versions.map(version => <details key={version.id} className="history-entry"><summary>Version {version.version} · {new Date(version.created_at).toLocaleString()} <ChevronRight size={15} /></summary><pre>{version.content}</pre><small>SHA-256: {version.content_sha256}</small></details>)}<h3>Responses and audit</h3>{detail.events.length ? detail.events.map((event, index) => <div className="history-event" key={`${event.version_id}-${index}`}><strong>{labels[event.action as AgreementStatus] || event.action}</strong><span>Version ID {event.version_id} · {event.verification_method.replaceAll('_', ' ')} · {new Date(event.created_at).toLocaleString()}</span>{event.note && <p>{event.note}</p>}</div>) : <p className="field-hint">No customer responses yet.</p>}<details className="audit-details"><summary>View audit history</summary>{detail.audit.map((event, index) => <div className="history-event" key={index}><strong>{event.action.replaceAll('_', ' ')}</strong><span>{new Date(event.created_at).toLocaleString()}</span>{event.detail && <p>{event.detail}</p>}</div>)}</details></div>
  </div>
}

export function AgreementsPage({ membership }: { membership: Membership }) {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [transactionId, setTransactionId] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const businessId = membership.business_id
  const enabled = membership.can_manage_agreements
  const { data: agreements = [], isPending, error: listError } = useQuery({ queryKey: ['agreements', businessId], queryFn: () => getAgreements(businessId), enabled, refetchInterval: 15000 })
  const { data: transactions = [] } = useQuery({ queryKey: ['transactions', businessId], queryFn: () => getTransactions(businessId), enabled })
  const { data: detail, isPending: detailPending, error: detailError } = useQuery({ queryKey: ['agreement', businessId, selectedId], queryFn: () => getAgreement(businessId, selectedId!), enabled: enabled && !!selectedId, refetchInterval: 15000 })
  const available = transactions.filter(item => item.balance_ugx > 0 && !agreements.some(agreement => agreement.transaction_id === item.id))
  const refresh = async () => { await queryClient.invalidateQueries({ queryKey: ['agreements', businessId] }); await queryClient.invalidateQueries({ queryKey: ['agreement', businessId, selectedId] }) }
  const create = async () => {
    if (!transactionId) return
    setBusy(true); setError(null)
    try { const created = await createAgreement(businessId, transactionId); setSelectedId(created.id); setTransactionId(''); await refresh() }
    catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  return <><div className="section-intro"><div><p className="eyebrow">AGREEMENT LIFECYCLE</p><h1>Agreements</h1><p>Prepare one credit-sale draft at a time, review every version, and preserve the customer's response.</p></div></div>{!enabled ? <div className="card module-card"><div className="empty-state"><h3>Agreement access not granted</h3><p>Ask the business owner to assign agreement management permission.</p></div></div> : <div className="agreements-layout"><div className="agreements-list-column"><div className="card form-card form-stack"><h3>Prepare an agreement</h3><p className="field-hint">Choose a saved credit transaction. The draft uses its recorded details; you can review and correct the full text before sharing.</p><label>Credit transaction<select value={transactionId} onChange={event => setTransactionId(event.target.value)}><option value="">Select a transaction</option>{available.map(item => <option key={item.id} value={item.id}>{item.counterparty_name} · {ugx(item.balance_ugx)} due</option>)}</select></label>{Boolean(error) && <ErrorMessage error={error} />}<Button onClick={create} disabled={busy || !transactionId}><Plus size={16} /> Create draft</Button>{available.length === 0 && <p className="field-hint">No unlinked credit transactions. <Link to="/transactions/new">Create one first.</Link></p>}</div><div className="card module-card"><h3>Agreement records</h3>{isPending ? <p className="field-hint">Loading agreements…</p> : listError ? <ErrorMessage error={listError} /> : agreements.length ? <div className="agreement-list">{agreements.map(item => <button key={item.id} className={`agreement-list-item ${selectedId === item.id ? 'selected' : ''}`} onClick={() => setSelectedId(item.id)}><span className="agreement-list-icon"><FileCheck2 size={19} /></span><span><strong>{item.counterparty_name}</strong><small>Version {item.current_version} · {ugx(item.balance_ugx)} due</small></span><span className={`agreement-status agreement-${item.status}`}>{labels[item.status]}</span></button>)}</div> : <div className="empty-state"><h3>No agreements yet</h3><p>Create a draft from a credit transaction.</p></div>}</div></div><div className="card agreement-detail-card">{!selectedId ? <div className="empty-state"><FileCheck2 size={28} /><h3>Select an agreement</h3><p>Open a record to review its exact terms and history.</p></div> : detailPending ? <p className="field-hint">Loading agreement…</p> : detailError ? <ErrorMessage error={detailError} /> : detail ? <AgreementEditor key={`${detail.id}-${detail.current_version}`} detail={detail} businessId={businessId} canArchive={membership.can_manage_documents} onChange={refresh} /> : null}</div></div>}</>
}

type ResponseMode = 'accept' | 'correction_requested' | 'rejected' | null

export function ExternalAgreementPage() {
  const location = useLocation()
  const token = new URLSearchParams(location.hash.slice(1)).get('token') || ''
  const { data: review, isPending, error: loadError, refetch } = useQuery({ queryKey: ['external-review', token], queryFn: () => getExternalReview(token), enabled: !!token, retry: false, gcTime: 0 })
  const [mode, setMode] = useState<ResponseMode>(null)
  const [note, setNote] = useState('')
  const [code, setCode] = useState('')
  const [developmentCode, setDevelopmentCode] = useState('')
  const [codeStatus, setCodeStatus] = useState('')
  const [checked, setChecked] = useState(false)
  const [outcome, setOutcome] = useState<string | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const requestCode = async () => { setBusy(true); setError(null); try { const result = await requestDevelopmentCode(token); setDevelopmentCode(result.development_code || ''); setCodeStatus(result.delivery === 'development' ? 'Development code shown below.' : `Code ${result.delivery_status} via ${result.delivery}. Check that channel; delivery is not guaranteed.`) } catch (failure) { setError(failure) } finally { setBusy(false) } }
  const accept = async () => {
    if (!review || !checked || !/^\d{6}$/.test(code)) return
    setBusy(true); setError(null)
    try { await acceptExternalAgreement(token, review.version_id, code); setOutcome('You explicitly accepted the displayed version. Legal identity was not independently verified.'); await refetch() }
    catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  const respond = async () => {
    if (!review || (mode !== 'correction_requested' && mode !== 'rejected')) return
    if (mode === 'correction_requested' && !note.trim()) { setError(new Error('Describe the correction you need.')); return }
    setBusy(true); setError(null)
    try { await respondExternalAgreement(token, review.version_id, mode, note); setOutcome(mode === 'rejected' ? 'Your rejection was recorded from this review link.' : 'Your correction request was recorded from this review link.'); setMode(null) }
    catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  return <div className="review-page"><header className="review-header"><div className="brand"><div className="brand-mark"><BookOpenCheck size={22} /></div><span>MyBiz<span className="brand-accent">Vault</span></span></div><span className="review-header-note"><ShieldCheck size={16} /> Focused agreement review</span></header><main className="review-container"><div className="review-label"><LockKeyhole size={14} /> TRANSACTION-SPECIFIC REVIEW LINK</div>{!token ? <div className="card form-card"><h1>Invitation unavailable</h1><p>This page needs a complete review link from the business.</p></div> : isPending ? <div className="card form-card">Loading agreement…</div> : loadError ? <div className="card form-card"><h1>Invitation unavailable</h1><p>The link may have expired, been replaced, or already received a correction or rejection.</p></div> : review && <><div className="review-intro"><p className="eyebrow">INVITED BY {review.business_name.toUpperCase()}</p><h1>{review.status === 'confirmed' ? 'Confirmed agreement' : 'Review your agreement'}</h1><p>For {review.counterparty_name} · Transaction {review.transaction_id} · Version {review.version}. Read the complete proposed terms before responding.</p></div><div className="review-card"><div className="review-card-head"><div><small>EXACT AGREEMENT VERSION</small><strong>Version {review.version}</strong></div><span className={`agreement-status agreement-${review.status}`}>{labels[review.status]}</span></div><div className="review-card-body"><pre className="agreement-document">{review.content}</pre><div className="review-amounts"><div><span>Total value</span><strong>{ugx(review.total_ugx)}</strong></div><div><span>Amount reported as paid</span><strong>{ugx(review.paid_ugx)}</strong></div><div className="amount-due"><span>Balance due</span><strong>{ugx(review.balance_ugx)}</strong></div></div><div className="hash-line"><LockKeyhole size={14} /> Version SHA-256: <code>{review.content_sha256}</code></div><div className="review-disclaimer"><CircleAlert size={19} /><span>MyBizVault has not independently verified the reported payment or the identity of the person using this link. A passcode records a response but does not itself establish a legal signature.</span></div></div></div>{outcome && <div className="review-outcome" role="status"><CheckCircle2 size={20} /> {outcome}</div>}{review.status === 'confirmed' ? <div className="review-actions"><h3>Confirmed version preserved</h3><p>This is the exact version recorded as accepted. Access through this review link ends when the link expires.</p></div> : !outcome && <div className="review-actions"><h3>Your response</h3><p>You can request a correction or reject these terms. Acceptance requires explicit confirmation of version {review.version} and a verification code.</p><div className="review-buttons"><Button onClick={() => setMode('accept')}>Review and accept</Button><Button variant="outline" onClick={() => setMode('correction_requested')}>Request correction</Button><Button variant="ghost" onClick={() => setMode('rejected')}>Reject</Button></div>{mode === 'accept' && <div className="response-panel"><h4>Accept version {review.version}</h4>{(review.development_verification || review.verification_delivery_available) ? <>{review.development_verification && <div className="dev-warning"><CircleAlert size={18} /><span>Development-only verification: the code is displayed here to the link holder. This does not prove customer identity.</span></div>}<Button variant="outline" onClick={requestCode} disabled={busy}>{busy ? 'Please wait…' : 'Show development code'}</Button>{codeStatus && <p role="status" className="field-hint">{codeStatus}</p>}{developmentCode && <p className="dev-code">Development code: <strong>{developmentCode}</strong></p>}<label>Enter the six-digit code<input inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ''))} /></label><label className="accept-check"><input type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)} /> I have read and explicitly accept agreement version {review.version} displayed above.</label><Button onClick={accept} disabled={busy || !checked || !/^\d{6}$/.test(code)}>Confirm acceptance</Button></> : <div className="dev-warning"><CircleAlert size={18} /><span>Acceptance is unavailable until independent code delivery is configured. You can still request a correction or reject.</span></div>}</div>}{(mode === 'correction_requested' || mode === 'rejected') && <div className="response-panel"><h4>{mode === 'rejected' ? 'Reject this version' : 'Request a correction'}</h4><label>{mode === 'rejected' ? 'Reason (optional)' : 'What should be corrected?'}<textarea rows={4} value={note} onChange={event => setNote(event.target.value)} maxLength={2000} /></label><p className="field-hint">This response is recorded from the link. It is not independently identity-verified.</p><Button onClick={respond} disabled={busy || (mode === 'correction_requested' && !note.trim())}>{busy ? 'Submitting…' : 'Submit response'}</Button></div>}{Boolean(error) && <ErrorMessage error={error} />}</div>}</>}</main></div>
}
