import { test } from 'node:test'
import assert from 'node:assert/strict'
import { suggestTransactionFromSpeech as suggest } from '../src/lib/voiceDraft.ts'

const now = new Date(2026, 10, 25)

test('extracts uppercase, currency, paid aliases and named deadline', () => {
  const result = suggest('TOTAL VALUE UGX 1,000,000. INITIAL PAID AMOUNT UGX 200000. PAYMENT DEADLINE 30 November 2026.', now)
  assert.equal(result.total_ugx, 1000000)
  assert.equal(result.paid_ugx, 200000)
  assert.equal(result.due_date, '2026-11-30')
})

test('extracts lowercase spoken money and payable by deadline', () => {
  const result = suggest('total amount one million shillings. the customer has paid two hundred thousand shillings. the balance is payable by November 30, 2026.', now)
  assert.equal(result.total_ugx, 1000000)
  assert.equal(result.paid_ugx, 200000)
  assert.equal(result.due_date, '2026-11-30')
})

test('extracts shorthand and relative dates', () => {
  const result = suggest('total payable 2m, down payment 200k, payment due in two weeks', now)
  assert.equal(result.total_ugx, 2000000)
  assert.equal(result.paid_ugx, 200000)
  assert.equal(result.due_date, '2026-12-09')
  assert.equal(suggest('due tomorrow', now).due_date, '2026-11-26')
  assert.equal(suggest('due next Friday', now).due_date, '2026-11-27')
})

test('flags ambiguity, missing and invalid values', () => {
  assert.equal(suggest('payment deadline 03/04/2026', now).due_date, undefined)
  assert.match(suggest('payment deadline 03/04/2026', now).uncertainties.join(' '), /ambiguous/)
  assert.equal(suggest('total value 100, initial payment 200', now).paid_ugx, undefined)
  assert.equal(suggest('initial payment -10', now).paid_ugx, undefined)
  assert.equal(suggest('initial payment', now).paid_ugx, undefined)
})

test('keeps initial payment distinct from total, flags balance conflict', () => {
  const result = suggest('initial payment 200000, total price 500000, outstanding balance 400000', now)
  assert.equal(result.total_ugx, 500000)
  assert.equal(result.paid_ugx, 200000)
  assert.match(result.uncertainties.join(' '), /Outstanding balance conflicts/)
})

test('does not confuse delivery or transaction dates with payment deadline', () => {
  const result = suggest('transaction date 2026-11-25, delivery date 2026-11-26, payment deadline 2026-11-30', now)
  assert.equal(result.due_date, '2026-11-30')
})

test('does not apply conflicting values', () => {
  const result = suggest('initial payment 200, paid initially 300, total value 1000, total payable 1100', now)
  assert.equal(result.paid_ugx, undefined)
  assert.equal(result.total_ugx, undefined)
  assert.match(result.uncertainties.join(' '), /Conflicting/)
})
