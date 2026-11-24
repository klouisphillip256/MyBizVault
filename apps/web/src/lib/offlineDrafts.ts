export interface TransactionDraftValues {
  counterparty_id: string
  description: string
  transaction_date: string
  total_ugx: number
  paid_ugx: number
  due_date: string
  delivery_notes: string
  line_items?: { description: string; quantity: number; unit_price_ugx: number }[]
}

export interface OfflineTransactionDraft {
  key: string
  user_id: string
  business_id: string
  request_id: string
  values: TransactionDraftValues
  state: 'draft' | 'pending' | 'needs_review'
  error: string | null
  updated_at: string
}

const databaseName = 'mybizvault-private-drafts'
const storeName = 'transaction-drafts'

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(databaseName, 1)
    request.onupgradeneeded = () => { request.result.createObjectStore(storeName, { keyPath: 'key' }) }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error('Local draft storage is unavailable'))
  })
}

function transact<T>(mode: IDBTransactionMode, operation: (store: IDBObjectStore, resolve: (value: T) => void) => IDBRequest | void): Promise<T> {
  return openDatabase().then(db => new Promise<T>((resolve, reject) => {
    const transaction = db.transaction(storeName, mode)
    let value: T
    transaction.oncomplete = () => { db.close(); resolve(value) }
    transaction.onerror = () => { db.close(); reject(transaction.error || new Error('Local draft operation failed')) }
    transaction.onabort = () => { db.close(); reject(transaction.error || new Error('Local draft operation failed')) }
    operation(transaction.objectStore(storeName), result => { value = result })
  }))
}

export const draftKey = (userId: string, businessId: string) => `${userId}:${businessId}`
export const getTransactionDraft = (key: string) => transact<OfflineTransactionDraft | null>('readonly', (store, resolve) => {
  const request = store.get(key)
  request.onsuccess = () => resolve((request.result as OfflineTransactionDraft | undefined) || null)
})
export const putTransactionDraft = (draft: OfflineTransactionDraft) => transact<void>('readwrite', store => { store.put(draft) })
export const deleteTransactionDraft = (key: string) => transact<void>('readwrite', store => { store.delete(key) })
export const clearUserDrafts = (userId: string) => transact<void>('readwrite', store => {
  const request = store.openCursor()
  request.onsuccess = () => {
    const cursor = request.result
    if (!cursor) return
    if ((cursor.value as OfflineTransactionDraft).user_id === userId) cursor.delete()
    cursor.continue()
  }
})
