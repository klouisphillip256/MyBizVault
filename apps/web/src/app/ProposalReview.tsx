import { useQuery } from '@tanstack/react-query'
import { BookOpenCheck, CheckCircle2, CircleAlert, LockKeyhole, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Button } from '../components/ui/button'
import { apiError, getExternalProposal, requestProposalCode, respondExternalProposal } from '../lib/api'
import { ugx } from '../lib/utils'

type Action = 'accepted' | 'declined' | 'correction_requested'

export function ProposalReviewPage() {
  const location = useLocation()
  const token = new URLSearchParams(location.hash.slice(1)).get('token') || ''
  const { data: review, isPending, error: loadError, refetch } = useQuery({ queryKey: ['proposal-review', token], queryFn: () => getExternalProposal(token), enabled: !!token, retry: false, gcTime: 0 })
  const [action, setAction] = useState<Action | null>(null)
  const [note, setNote] = useState('')
  const [code, setCode] = useState('')
  const [developmentCode, setDevelopmentCode] = useState('')
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [outcome, setOutcome] = useState('')
  const getCode = async () => { setBusy(true); setError(null); try { setDevelopmentCode((await requestProposalCode(token)).development_code) } catch (failure) { setError(failure) } finally { setBusy(false) } }
  const submit = async () => {
    if (!review || !action) return
    if (action === 'accepted' && (!checked || !/^\d{6}$/.test(code))) return
    if (action === 'correction_requested' && !note.trim()) { setError(new Error('Describe the correction requested.')); return }
    setBusy(true); setError(null)
    try {
      await respondExternalProposal(token, { proposal_id: review.proposal_id, action, note: note.trim(), code: action === 'accepted' ? code : undefined, explicitly_accepted: action === 'accepted' && checked })
      setOutcome(`Your ${action.replaceAll('_', ' ')} response was recorded from this link. Identity was not independently verified.`)
      setAction(null)
      await refetch()
    } catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  return <div className="review-page"><header className="review-header"><div className="brand"><div className="brand-mark"><BookOpenCheck size={22} /></div><span>MyBiz<span className="brand-accent">Vault</span></span></div><span className="review-header-note"><ShieldCheck size={16} /> Focused proposal review</span></header><main className="review-container"><div className="review-label"><LockKeyhole size={14} /> TRANSACTION-SPECIFIC REVIEW LINK</div>{!token ? <div className="card form-card"><h1>Invitation unavailable</h1><p>Open the complete link shared by the business.</p></div> : isPending ? <div className="card form-card">Loading proposal…</div> : loadError ? <div className="card form-card"><h1>Invitation unavailable</h1><p>The link may have expired or been replaced.</p></div> : review && <><div className="review-intro"><p className="eyebrow">INVITED BY {review.business_name.toUpperCase()}</p><h1>Review a proposed change</h1><p>For {review.counterparty_name}. Read the original transaction details and complete proposal before responding.</p></div><div className="review-card"><div className="review-card-head"><div><small>PROPOSAL TYPE</small><strong>{review.kind.replaceAll('_', ' ')}</strong></div><span className="agreement-status">{review.status.replaceAll('_', ' ')}</span></div><div className="review-card-body"><h2>Proposed terms</h2><pre className="agreement-document">{review.proposal}</pre><div className="review-amounts"><div><span>Original transaction</span><strong>{review.transaction_description}</strong></div><div><span>Total value</span><strong>{ugx(review.total_ugx)}</strong></div><div><span>Initially reported paid</span><strong>{ugx(review.initial_paid_ugx)}</strong></div><div><span>Original deadline</span><strong>{review.original_due_date || 'None'}</strong></div>{review.proposed_due_date && <div><span>Proposed deadline</span><strong>{review.proposed_due_date}</strong></div>}{review.proposed_amount_ugx && <div><span>Proposed amount</span><strong>{ugx(review.proposed_amount_ugx)}</strong></div>}</div><div className="review-disclaimer"><CircleAlert size={19} /><span>This local prototype does not independently verify your identity or reported payments. A displayed development code is not a legal signature. Acceptance records a response to this proposal and does not process money or rewrite the original agreement.</span></div></div></div>{outcome && <div className="review-outcome" role="status"><CheckCircle2 size={20} /> {outcome}</div>}{review.status === 'open' && !outcome && <div className="review-actions"><h3>Your response</h3><div className="review-buttons">{review.kind !== 'payment_dispute' && <Button onClick={() => setAction('accepted')}>Review and accept</Button>}<Button variant="outline" onClick={() => setAction('correction_requested')}>Request correction</Button><Button variant="ghost" onClick={() => setAction('declined')}>Decline</Button></div>{action && <div className="response-panel"><h4>{action.replaceAll('_', ' ')}</h4>{action === 'accepted' ? review.development_verification ? <><div className="dev-warning"><CircleAlert size={18} /><span>Development code is shown to the link holder. It does not prove customer identity.</span></div><Button variant="outline" onClick={getCode} disabled={busy}>Show development code</Button>{developmentCode && <p className="dev-code">Development code: <strong>{developmentCode}</strong></p>}<label>Six-digit code<input value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ''))} inputMode="numeric" maxLength={6} /></label><label className="accept-check"><input type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)} /> I have read and explicitly accept the proposal displayed above.</label></> : <div className="dev-warning"><CircleAlert size={18} /><span>Acceptance is unavailable until independent code delivery is configured.</span></div> : <label>Reason {action === 'correction_requested' ? '(required)' : '(optional)'}<textarea value={note} onChange={event => setNote(event.target.value)} maxLength={2000} rows={3} /></label>}{(action !== 'accepted' || review.development_verification) && <Button onClick={submit} disabled={busy || (action === 'accepted' && (!checked || !/^\d{6}$/.test(code))) || (action === 'correction_requested' && !note.trim())}>Submit response</Button>}</div>}{Boolean(error) && <div role="alert" className="form-error">{apiError(error)}</div>}</div>}</>}</main></div>
}
