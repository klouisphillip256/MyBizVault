export interface VoiceSuggestion {
  description: string
  total_ugx?: number
  paid_ugx?: number
  due_date?: string
  uncertainties: string[]
}

function amount(text: string, label: string): number | undefined {
  const match = text.match(new RegExp(`\\b${label}\\s*(?:is|of|:)?\\s*(?:UGX|shillings)?\\s*([0-9][0-9,]*)`, 'i'))
  if (!match) return undefined
  const value = Number(match[1].replaceAll(',', ''))
  return Number.isSafeInteger(value) && value >= 0 ? value : undefined
}

export function suggestTransactionFromSpeech(transcript: string): VoiceSuggestion {
  const description = transcript.trim().replace(/\s+/g, ' ')
  const total = amount(description, '(?:total|price|value)')
  const paid = amount(description, '(?:paid|deposit)')
  const dueMatch = description.match(/\b(?:due|deadline)\s*(?:on|is|:)?\s*(\d{4}-\d{2}-\d{2})\b/i)
  const due = dueMatch && !Number.isNaN(Date.parse(dueMatch[1])) ? dueMatch[1] : undefined
  const uncertainties: string[] = []
  if (total === undefined) uncertainties.push('Total value was not recognised.')
  if (paid === undefined) uncertainties.push('Initial paid amount was not recognised.')
  if (!due) uncertainties.push('Payment deadline was not recognised. Enter an ISO date (YYYY-MM-DD) if a balance remains.')
  if (total !== undefined && paid !== undefined && paid > total) uncertainties.push('Recognised paid amount exceeds the total; check both amounts.')
  return { description, total_ugx: total, paid_ugx: paid, due_date: due, uncertainties }
}
