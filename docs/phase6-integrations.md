# Phase 6 integration and offline boundaries

## Offline drafts

The transaction form stores one user-and-business-scoped draft in IndexedDB after an explicit save or an offline submit. It keeps a request UUID across retries. The API enforces uniqueness per business, returns the same transaction for an identical retry, and rejects use of that UUID with different transaction facts. Server validation, deleted contacts, expired sessions, and changed permissions leave a draft for manual review. The client does not queue agreement acceptance, payments, documents, or proposal responses. Logging out clears local transaction drafts. Browser storage is not encrypted, and a device backup may retain it. No authenticated API response or Vault document is cached by a service worker.

## Speech

The browser's speech recognition API is optional. MyBizVault does not record audio. Speech may be processed by a browser vendor and may not work offline. A transcript stays in page memory, and its simple extractor suggests a description, integer UGX amounts, and an ISO deadline. Uncertain or missing values are flagged. Applying suggestions and saving are separate user actions. A production offline speech model would need a model-size, device-support, privacy, and accuracy evaluation.

## Email and SMS

Business users explicitly choose to send a newly generated agreement or proposal review link. SMTP uses STARTTLS; the SMS adapter posts JSON to an operator-configured HTTPS endpoint with a bearer token. Delivery capabilities appear only when configured. The provider credentials live in server environment secrets. If delivery fails after a link is created, the API returns that link so the user can share it manually; reissuing a link revokes the previous one. No background reminders or bulk messaging are enabled. Before production, choose providers, validate delivery receipts and retries, add abuse/rate controls, and obtain the right messaging consent.

The current development code is shown to the link holder. It proves neither control of the contact channel nor identity. Production acceptance remains disabled until a separately delivered, verifiable code mechanism is implemented and tested.

## USSD exploration

USSD is suitable for a short response to a known transaction reference, not for displaying full agreement text or documents. A future flow would send an out-of-band reference, ask for limited confirmation only after the complete terms were delivered through an accessible channel, and bind each session to one transaction and version. It needs a telecom aggregator, short-code provisioning, language and accessibility review, replay protection, session timeouts, consent records, and provider-specific security tests. No USSD endpoint or customer identity claim is implemented in this prototype.

## Additional legal templates

The existing credit-sale agreement is the only live legal template. Additional employment or other contract templates need reviewed clauses, required fields, jurisdiction rules, versioned content, and separate acceptance criteria. The system must not invent legal terms or imply that one template covers every transaction. Add those templates only after that content and review are available.
