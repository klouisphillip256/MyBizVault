import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '../components/ui/button'
import { apiError, createConsultationRequest, getConsultationRequests, getLawyerProfiles } from '../lib/api'
import type { Membership } from '../types/domain'

const issueTypes = [
  ['business', 'Business law'], ['contracts', 'Contracts'], ['employment', 'Employment'],
  ['debt', 'Debt recovery'], ['supplier', 'Supplier agreement'], ['dispute', 'Dispute'], ['mediation', 'Mediation'],
]

export function FindLawyerPage({ membership }: { membership: Membership }) {
  const [issueType, setIssueType] = useState('business')
  const [profileId, setProfileId] = useState('')
  const [summary, setSummary] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [notice, setNotice] = useState('')
  const queryClient = useQueryClient()
  const businessId = membership.business_id
  const owner = membership.role === 'owner'
  const { data: profiles = [], isPending } = useQuery({ queryKey: ['lawyer-profiles', issueType], queryFn: () => getLawyerProfiles(issueType) })
  const { data: requests = [] } = useQuery({ queryKey: ['consultation-requests', businessId], queryFn: () => getConsultationRequests(businessId), enabled: owner })
  const selected = profiles.find(item => item.id === profileId)
  const save = async () => {
    if (!selected || summary.trim().length < 20) return
    setBusy(true); setError(null); setNotice('')
    try {
      await createConsultationRequest(businessId, { profile_id: selected.id, issue_type: issueType, issue_summary: summary.trim() })
      await queryClient.invalidateQueries({ queryKey: ['consultation-requests', businessId] })
      setSummary(''); setProfileId(''); setNotice('Request saved privately in this business workspace. No lawyer has been contacted.')
    } catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  return <><div className="section-intro"><div><p className="eyebrow">DEMONSTRATION DIRECTORY</p><h1>Find a Lawyer</h1><p>Browse fictional legal profiles by issue. Consultation requests stay private until a real marketplace is available.</p></div></div>
    <div className="card form-card legal-filters"><label>Type of legal issue<select value={issueType} onChange={event => { setIssueType(event.target.value); setProfileId(''); setNotice('') }}>{issueTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
    {isPending ? <p>Loading demonstration profiles…</p> : <div className="legal-grid">{profiles.map(profile => <article className="card module-card lawyer-profile" key={profile.id}><p className="eyebrow">FICTIONAL PROFILE</p><h2>{profile.name}</h2><strong>{profile.specialization}</strong><p>Location: {profile.location}</p><p>Consultation: {profile.consultation_method}</p><p>Availability: {profile.availability}</p>{owner && <Button variant="outline" onClick={() => { setProfileId(profile.id); setNotice('') }}>Request consultation</Button>}</article>)}</div>}
    {owner ? <><div className="card form-card form-stack lawyer-request"><h2>Consultation request</h2><p>{selected ? `Profile: ${selected.name}` : 'Choose a demonstration profile above.'}</p><label>Describe the legal issue<textarea rows={4} value={summary} onChange={event => setSummary(event.target.value)} maxLength={2000} placeholder="Describe the issue without attaching confidential records." /></label><p className="field-hint">This saves a private draft. It is not sent to a lawyer or law firm.</p>{Boolean(error) && <div role="alert" className="form-error">{apiError(error)}</div>}{notice && <p role="status">{notice}</p>}<Button onClick={save} disabled={busy || !selected || summary.trim().length < 20}>{busy ? 'Saving…' : 'Save consultation request'}</Button></div><div className="card module-card lawyer-request"><h2>Saved requests</h2>{requests.length ? requests.map(request => <div className="obligation-entry" key={request.id}><strong>{profiles.find(item => item.id === request.profile_id)?.name || request.profile_id} · {request.status}</strong><small>{new Date(request.created_at).toLocaleString()} · {request.issue_type}</small><p>{request.issue_summary}</p></div>) : <p className="field-hint">No requests saved for this business.</p>}</div></> : <div className="card module-card"><p>Only the business owner can save a consultation request.</p></div>}
    <p className="field-hint">All profiles, availability and names are fictional. No partnership, professional verification or automatic allocation is implied.</p></>
}
