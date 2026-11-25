export interface VoiceSuggestion {
  description: string
  total_ugx?: number
  paid_ugx?: number
  due_date?: string
  uncertainties: string[]
}

const aliases = {
  total: ['transaction value', 'total payable', 'total amount', 'total value', 'total cost', 'total price', 'price', 'value'],
  paid: ['initial paid amount', 'initial amount paid', 'customer has paid', 'amount already paid', 'upfront payment', 'advance payment', 'initial payment', 'down payment', 'amount paid', 'paid initially', 'deposit', 'paid'],
  due: ['payment deadline date', 'payment due date', 'balance due by', 'payment deadline', 'payment due', 'payable by', 'due date', 'deadline', 'due'],
  balance: ['outstanding balance', 'outstanding payment', 'remaining balance', 'remaining amount', 'unpaid amount', 'amount owed'],
  otherDate: ['delivery date', 'transaction date'],
}
const words: Record<string, number> = { zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19, twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90 }
const months = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
const weekdays = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
const labels = Object.values(aliases).flat().sort((a, b) => b.length - a.length)
const pattern = new RegExp('\\b(?:' + labels.join('|').replaceAll(' ', '\\s+') + ')\\b', 'gi')

function parseAmount(input: string): number | undefined {
  const text = input.toLowerCase().replace(/^[\s:;,.]*(?:is|of|was|are)?\s*(?:ugx|ush|shillings?)?\s*/i, '')
  const digits = text.match(/^(-?\d[\d,]*(?:\.\d+)?)\s*([km])?\b/i)
  if (digits) {
    const value = Number(digits[1].replaceAll(',', '')) * (digits[2]?.toLowerCase() === 'k' ? 1000 : digits[2]?.toLowerCase() === 'm' ? 1000000 : 1)
    return Number.isSafeInteger(value) && value >= 0 ? value : undefined
  }
  let value = 0, group = 0, found = false
  for (const word of text.replaceAll('-', ' ').split(/\s+/)) {
    if (word === 'and') continue
    if (word in words) { group += words[word]; found = true }
    else if (word === 'hundred') { group *= 100; found = true }
    else if (word === 'thousand' || word === 'million') { value += group * (word === 'thousand' ? 1000 : 1000000); group = 0; found = true }
    else break
  }
  const result = value + group
  return found && Number.isSafeInteger(result) && result >= 0 ? result : undefined
}

function localDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function parseDate(input: string, now: Date): { value?: string; uncertain?: string } {
  const text = input.toLowerCase().replace(/^[\s:;,.-]*(?:is|on|of|will be)?\s*/i, '')
  const iso = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})\b/)
  const namedDay = text.match(/^(\d{1,2})\s+([a-z]+)\s+(\d{4})\b/)
  const namedMonth = text.match(/^([a-z]+)\s+(\d{1,2}),?\s+(\d{4})\b/)
  const slash = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})\b/)
  let year: number | undefined, month: number | undefined, day: number | undefined
  if (iso) { year = Number(iso[1]); month = Number(iso[2]); day = Number(iso[3]) }
  else if (namedDay) { year = Number(namedDay[3]); month = months.indexOf(namedDay[2]) + 1; day = Number(namedDay[1]) }
  else if (namedMonth) { year = Number(namedMonth[3]); month = months.indexOf(namedMonth[1]) + 1; day = Number(namedMonth[2]) }
  else if (slash) {
    day = Number(slash[1]); month = Number(slash[2]); year = Number(slash[3])
    if (day <= 12 && month <= 12 && day !== month) return { uncertain: 'Payment deadline is ambiguous; confirm day and month manually.' }
  } else if (/^tomorrow\b/.test(text)) return { value: localDate(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)) }
  else if (/^next\s+(sunday|monday|tuesday|wednesday|thursday|friday|saturday)\b/.test(text)) {
    const target = weekdays.indexOf(text.match(/^next\s+(\w+)/)![1])
    const days = ((target - now.getDay() + 7) % 7) || 7
    return { value: localDate(new Date(now.getFullYear(), now.getMonth(), now.getDate() + days)) }
  } else if (/^in\s+two\s+weeks\b/.test(text)) return { value: localDate(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 14)) }
  else return { uncertain: 'Payment deadline was not recognised; confirm it manually.' }
  if (!year || !month || !day) return { uncertain: 'Payment deadline was not recognised; confirm it manually.' }
  const date = new Date(year, month - 1, day)
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? { value: localDate(date) } : { uncertain: 'Payment deadline is invalid; confirm it manually.' }
}

export function suggestTransactionFromSpeech(transcript: string, now = new Date()): VoiceSuggestion {
  const description = transcript.trim().replace(/\s+/g, ' ')
  const normalized = description.replace(/[“”]/g, '"').replace(/[–—]/g, '-')
  const matches = [...normalized.matchAll(pattern)]
  const uncertainties: string[] = []
  let total: number | undefined, paid: number | undefined, due: string | undefined, balance: number | undefined
  let totalConflict = false, paidConflict = false, dueConflict = false
  for (let i = 0; i < matches.length; i++) {
    const match = matches[i], label = match[0].toLowerCase().replace(/\s+/g, ' ')
    const next = normalized.slice(match.index! + match[0].length, matches[i + 1]?.index ?? normalized.length)
    if (aliases.total.includes(label) || aliases.paid.includes(label) || aliases.balance.includes(label)) {
      const value = parseAmount(next)
      if (value === undefined) { uncertainties.push(`${label} needs a valid amount; confirm it manually.`); continue }
      if (aliases.total.includes(label)) { if (total !== undefined && total !== value) { totalConflict = true; uncertainties.push('Conflicting total values; confirm manually.') } else total = value }
      else if (aliases.paid.includes(label)) { if (paid !== undefined && paid !== value) { paidConflict = true; uncertainties.push('Conflicting initial payments; confirm manually.') } else paid = value }
      else { if (balance !== undefined && balance !== value) uncertainties.push('Conflicting outstanding balances; confirm manually.'); else balance = value }
    } else if (aliases.due.includes(label)) {
      const result = parseDate(next, now)
      if (result.uncertain) uncertainties.push(result.uncertain)
      else if (due && due !== result.value) { dueConflict = true; uncertainties.push('Conflicting payment deadlines; confirm manually.') }
      else due = result.value
    }
  }
  if (totalConflict) total = undefined
  if (paidConflict) paid = undefined
  if (dueConflict) due = undefined
  if (total === undefined) uncertainties.push('Total value was not recognised.')
  if (paid === undefined) uncertainties.push('Initial paid amount was not recognised.')
  if (!due) uncertainties.push('Payment deadline was not recognised; confirm it manually if a balance remains.')
  if (total !== undefined && paid !== undefined && paid > total) { uncertainties.push('Initial payment exceeds the total; confirm both amounts.'); paid = undefined }
  if (balance !== undefined && total !== undefined && paid !== undefined && balance !== total - paid) uncertainties.push('Outstanding balance conflicts with total minus initial payment; confirm manually.')
  return { description, total_ugx: total, paid_ugx: paid, due_date: due, uncertainties: [...new Set(uncertainties)] }
}
