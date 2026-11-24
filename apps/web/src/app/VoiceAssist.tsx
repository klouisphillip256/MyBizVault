import { Mic, MicOff } from 'lucide-react'
import { useRef, useState } from 'react'
import { Button } from '../components/ui/button'
import { suggestTransactionFromSpeech } from '../lib/voiceDraft'
import type { TransactionDraftValues } from '../lib/offlineDrafts'

interface Recognition {
  lang: string
  interimResults: boolean
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onerror: (() => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
}
type SpeechWindow = Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition }

export function VoiceAssist({ apply }: { apply: (values: Partial<TransactionDraftValues>) => void }) {
  const [transcript, setTranscript] = useState('')
  const [listening, setListening] = useState(false)
  const [error, setError] = useState('')
  const recognition = useRef<Recognition | null>(null)
  const speechWindow = window as SpeechWindow
  const constructor = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition
  const suggestion = suggestTransactionFromSpeech(transcript)
  const start = () => {
    if (!constructor) return
    setError('')
    try {
      const session = new constructor()
      session.lang = 'en-UG'
      session.interimResults = false
      session.onresult = event => {
        const latest = event.results[event.results.length - 1]
        setTranscript(latest?.[0]?.transcript || '')
      }
      session.onerror = () => { setError('Microphone or speech recognition is unavailable. You can type the notes below.'); setListening(false) }
      session.onend = () => setListening(false)
      recognition.current = session
      session.start()
      setListening(true)
    } catch { setError('Could not start speech recognition. You can type the notes below.') }
  }
  const stop = () => { recognition.current?.stop(); setListening(false) }
  const applySuggestion = () => {
    if (!suggestion.description) return
    apply({ description: suggestion.description,
      ...(suggestion.total_ugx !== undefined ? { total_ugx: suggestion.total_ugx } : {}),
      ...(suggestion.paid_ugx !== undefined && (suggestion.total_ugx === undefined || suggestion.paid_ugx <= suggestion.total_ugx) ? { paid_ugx: suggestion.paid_ugx } : {}),
      ...(suggestion.due_date ? { due_date: suggestion.due_date } : {}) })
  }
  return <div className="voice-assist"><h3>Voice-assisted entry</h3><p>Speak or type a description, then review every suggested field before applying it. No audio recording is saved by MyBizVault.</p><div className="voice-actions">{constructor ? <Button type="button" variant="outline" onClick={listening ? stop : start}>{listening ? <MicOff size={16} /> : <Mic size={16} />}{listening ? 'Stop listening' : 'Speak transaction details'}</Button> : <span className="field-hint">This browser does not offer speech recognition. You can still type below.</span>}</div><label>Transcript to review<textarea value={transcript} onChange={event => setTranscript(event.target.value)} rows={3} placeholder="e.g. Supplied wholesale goods, total UGX 1000000, paid UGX 700000, due 2026-12-01" /></label>{error && <p className="form-error">{error}</p>}{transcript.trim() && <><div className="voice-suggestions"><strong>Suggested fields</strong><span>Total: {suggestion.total_ugx ?? 'check manually'} · Paid: {suggestion.paid_ugx ?? 'check manually'} · Due: {suggestion.due_date ?? 'check manually'}</span>{suggestion.uncertainties.map(item => <small key={item}>{item}</small>)}</div><Button type="button" variant="outline" onClick={applySuggestion}>Apply suggestions to form</Button></>}<small>Browser speech recognition may use an external service and may require connectivity. Review the form before saving.</small></div>
}
