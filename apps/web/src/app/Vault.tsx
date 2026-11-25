import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, ChevronRight, Download, FileImage, FileText, FolderClosed, LockKeyhole, Plus, Search, ShieldCheck, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '../components/ui/button'
import { apiError, createContractDraft, getDocument, getDocumentBlob, listDocuments, uploadDocument, uploadDocumentVersion } from '../lib/api'
import type { DocumentCategory, DocumentDetail, DocumentVersion, Membership } from '../types/domain'

const labels: Record<DocumentCategory, string> = { agreement: 'Agreement', contract: 'Contract', receipt: 'Receipt', image: 'Image', other: 'Other' }
const maxSize = 10 * 1024 * 1024

function ErrorMessage({ error }: { error: unknown }) { return <div role="alert" className="form-error">{apiError(error)}</div> }

function FilePreview({ businessId, documentId, version }: { businessId: string; documentId: string; version: DocumentVersion }) {
  const { data: blob, isPending, error } = useQuery({ queryKey: ['document-bytes', businessId, documentId, version.version], queryFn: () => getDocumentBlob(businessId, documentId, version.version), retry: false, gcTime: 0 })
  const [url, setUrl] = useState<string | null>(null)
  const [text, setText] = useState<string | null>(null)
  useEffect(() => {
    if (!blob) return
    const objectUrl = URL.createObjectURL(blob)
    setUrl(objectUrl)
    if (version.content_type.startsWith('text/plain')) {
      let active = true
      blob.text().then(value => { if (active) setText(value) })
      return () => { active = false; URL.revokeObjectURL(objectUrl) }
    }
    return () => URL.revokeObjectURL(objectUrl)
  }, [blob, version.content_type])
  if (isPending) return <div className="vault-preview-empty">Checking file integrity and loading preview…</div>
  if (error) return <ErrorMessage error={error} />
  if (version.content_type.startsWith('text/plain')) return <pre className="vault-text-preview">{text || 'Loading text…'}</pre>
  if (!url) return <div className="vault-preview-empty">Preparing preview…</div>
  if (version.content_type.startsWith('image/')) return <img className="vault-image-preview" src={url} alt={version.filename} />
  return <iframe className="vault-pdf-preview" src={url} title={`Preview of ${version.filename}`} />
}

function DetailPanel({ document, businessId, canManage, onChanged }: { document: DocumentDetail; businessId: string; canManage: boolean; onChanged: () => Promise<void> }) {
  const [selectedVersion, setSelectedVersion] = useState(document.current_version)
  const [newFile, setNewFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const version = document.versions.find(item => item.version === selectedVersion) || document.versions[0]
  const addVersion = async () => {
    if (!newFile) return
    if (newFile.size > maxSize) { setError(new Error('Files must be 10 MB or smaller.')); return }
    setBusy(true); setError(null)
    try { await uploadDocumentVersion(businessId, document.id, newFile); setNewFile(null); if (inputRef.current) inputRef.current.value = ''; await onChanged() }
    catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  const download = async () => {
    setBusy(true); setError(null)
    try {
      const blob = await getDocumentBlob(businessId, document.id, version.version, true)
      const url = URL.createObjectURL(blob)
      const anchor = window.document.createElement('a')
      anchor.href = url; anchor.download = version.filename; window.document.body.appendChild(anchor); anchor.click(); anchor.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 2000)
      await onChanged()
    } catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  return <div className="vault-detail"><div className="vault-detail-head"><div><p className="eyebrow">{labels[document.category].toUpperCase()} · {document.source === 'agreement' ? 'PRESERVED AGREEMENT' : 'PRIVATE UPLOAD'}</p><h2>{document.title}</h2><p>Version {document.current_version} · Added {new Date(document.created_at).toLocaleString()}</p></div><div className="vault-lock"><LockKeyhole size={17} /> Private</div></div><div className="vault-version-bar"><label>Version<select value={selectedVersion} onChange={event => setSelectedVersion(Number(event.target.value))}>{document.versions.map(item => <option key={item.id} value={item.version}>Version {item.version} · {item.filename}</option>)}</select></label><Button variant="outline" onClick={download} disabled={busy}><Download size={16} /> Download</Button></div><div className="vault-preview"><FilePreview key={`${document.id}-${version.version}`} businessId={businessId} documentId={document.id} version={version} /></div><div className="vault-integrity"><CheckCircle2 size={17} /><div><strong>Integrity checked when opened</strong><span>SHA-256: {version.sha256}</span><span>{new Intl.NumberFormat().format(version.size_bytes)} bytes · {version.content_type}</span></div></div>{Boolean(error) && <ErrorMessage error={error} />}{canManage && document.source === 'upload' && <div className="vault-new-version"><h3>Upload a new version</h3><p>Previous versions remain available and cannot be silently overwritten.</p><input ref={inputRef} type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={event => setNewFile(event.target.files?.[0] || null)} /><Button onClick={addVersion} disabled={busy || !newFile}><Upload size={16} /> Save new version</Button></div>}<div className="vault-events"><h3>Version and retrieval history</h3>{document.events.map((event, index) => <div className="vault-event" key={`${event.version_id}-${index}`}><span>{event.action.replaceAll('_', ' ')}</span><small>{new Date(event.created_at).toLocaleString()}</small></div>)}</div></div>
}

function ContractDraftForm({ businessId, onCreated }: { businessId: string; onCreated: (id: string) => Promise<void> }) {
  const [title, setTitle] = useState('')
  const [counterparty, setCounterparty] = useState('')
  const [purpose, setPurpose] = useState('')
  const [paymentTerms, setPaymentTerms] = useState('')
  const [obligations, setObligations] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const save = async () => {
    setBusy(true); setError(null)
    try {
      const result = await createContractDraft(businessId, { title: title.trim(), counterparty_name: counterparty.trim(), purpose: purpose.trim(), payment_terms: paymentTerms.trim(), obligations: obligations.trim() })
      await onCreated(result.id)
      setTitle(''); setCounterparty(''); setPurpose(''); setPaymentTerms(''); setObligations('')
    } catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  return <div className="card form-card form-stack"><h3>Create a contract draft</h3><p className="field-hint">Save a draft PDF in this Vault for review. No signature or acceptance is recorded.</p><label>Title<input value={title} onChange={event => setTitle(event.target.value)} maxLength={180} /></label><label>Other party<input value={counterparty} onChange={event => setCounterparty(event.target.value)} maxLength={160} /></label><label>Purpose and subject<textarea value={purpose} onChange={event => setPurpose(event.target.value)} rows={3} maxLength={3000} /></label><label>Payment terms<textarea value={paymentTerms} onChange={event => setPaymentTerms(event.target.value)} rows={2} maxLength={2000} /></label><label>Obligations and delivery<textarea value={obligations} onChange={event => setObligations(event.target.value)} rows={3} maxLength={3000} /></label>{Boolean(error) && <ErrorMessage error={error} />}<Button onClick={save} disabled={busy || title.trim().length < 3 || counterparty.trim().length < 2 || purpose.trim().length < 10 || paymentTerms.trim().length < 5 || obligations.trim().length < 10}>{busy ? 'Saving…' : 'Save contract draft'}</Button></div>
}

export function VaultPage({ membership }: { membership: Membership }) {
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const selectedId = params.get('document')
  const [searchText, setSearchText] = useState('')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [title, setTitle] = useState('')
  const [uploadCategory, setUploadCategory] = useState<Exclude<DocumentCategory, 'agreement'>>('receipt')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const businessId = membership.business_id
  const canView = membership.can_view_documents
  const { data: documents = [], isPending, error: listError } = useQuery({ queryKey: ['documents', businessId, query, category], queryFn: () => listDocuments(businessId, query, category), enabled: canView })
  const { data: detail, isPending: detailPending, error: detailError } = useQuery({ queryKey: ['document', businessId, selectedId], queryFn: () => getDocument(businessId, selectedId!), enabled: canView && !!selectedId })
  const refresh = async () => { await queryClient.invalidateQueries({ queryKey: ['documents', businessId] }); await queryClient.invalidateQueries({ queryKey: ['document', businessId, selectedId] }) }
  const upload = async () => {
    if (!file || !title.trim()) return
    if (file.size > maxSize) { setError(new Error('Files must be 10 MB or smaller.')); return }
    setBusy(true); setError(null)
    try { const created = await uploadDocument(businessId, title, uploadCategory, file); setTitle(''); setFile(null); if (inputRef.current) inputRef.current.value = ''; setParams({ document: created.id }); await refresh() }
    catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  return <><div className="section-intro"><div><p className="eyebrow">PRIVATE BUSINESS RECORDS</p><h1>Document Vault</h1><p>Find agreements, receipts and supporting files with their version and integrity history.</p></div></div>{!canView ? <div className="card module-card"><div className="empty-state"><h3>Vault access not granted</h3><p>Ask your business owner for document-viewing permission.</p></div></div> : <div className="vault-layout"><div className="vault-list-column">{membership.can_manage_documents && <ContractDraftForm businessId={businessId} onCreated={async id => { setParams({ document: id }); await refresh() }} />}<div className="card form-card"><h3>Find a document</h3><form className="vault-search" onSubmit={event => { event.preventDefault(); setQuery(searchText.trim()) }}><label>Search title or filename<input value={searchText} onChange={event => setSearchText(event.target.value)} placeholder="Search documents" maxLength={100} /></label><Button type="submit" variant="outline"><Search size={16} /> Search</Button></form><label className="vault-filter">Category<select value={category} onChange={event => setCategory(event.target.value)}><option value="">All categories</option>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div><div className="card module-card"><h3>Documents</h3>{isPending ? <p className="field-hint">Loading documents…</p> : listError ? <ErrorMessage error={listError} /> : documents.length ? <div className="vault-list">{documents.map(item => <button key={item.id} className={`vault-list-item ${selectedId === item.id ? 'selected' : ''}`} onClick={() => setParams({ document: item.id })}><span className="vault-list-icon">{item.current_file.content_type.startsWith('image/') ? <FileImage size={19} /> : <FileText size={19} />}</span><span><strong>{item.title}</strong><small>{labels[item.category]} · Version {item.current_version} · {item.current_file.filename}</small></span><ChevronRight size={16} /></button>)}</div> : <div className="empty-state"><FolderClosed size={28} /><h3>No documents found</h3><p>{query || category ? 'Try a different search or category.' : 'Upload a receipt or contract, or confirm an agreement to preserve it here.'}</p></div>}</div>{membership.can_manage_documents && <div className="card form-card form-stack"><h3>Add a document</h3><label>Title<input value={title} onChange={event => setTitle(event.target.value)} minLength={2} maxLength={180} placeholder="e.g. Bosco delivery receipt" /></label><label>Category<select value={uploadCategory} onChange={event => setUploadCategory(event.target.value as Exclude<DocumentCategory, 'agreement'>)}><option value="receipt">Receipt</option><option value="contract">Contract</option><option value="image">Image</option><option value="other">Other</option></select></label><label>PDF, PNG or JPEG (10 MB max)<input ref={inputRef} type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={event => setFile(event.target.files?.[0] || null)} /></label>{Boolean(error) && <ErrorMessage error={error} />}<Button onClick={upload} disabled={busy || !title.trim() || !file}><Plus size={16} /> {busy ? 'Uploading…' : 'Upload document'}</Button><p className="field-hint">Files stay private and are served only after business permission checks.</p></div>}</div><div className="card vault-detail-card">{!selectedId ? <div className="empty-state"><ShieldCheck size={28} /><h3>Select a document</h3><p>Preview a file, inspect its history, or download an authorised version.</p></div> : detailPending ? <p className="field-hint">Loading document…</p> : detailError ? <ErrorMessage error={detailError} /> : detail ? <DetailPanel key={`${detail.id}-${detail.current_version}`} document={detail} businessId={businessId} canManage={membership.can_manage_documents} onChanged={refresh} /> : null}</div></div>}</>
}
