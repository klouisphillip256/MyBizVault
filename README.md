# MyBizVault

The frontend lives in `apps/web` and the API in `services/api`; they are deployed as separate services from one repository. See the [trial hosting plan](docs/deployment.md) for the Railway setup and required environment variables.

Phase 6 working prototype for a mobile-first commercial documentation platform. Business accounts, staff permissions, customers, transactions, credit-sale agreements, document metadata, payments, and proposal history are persisted in SQLite locally. Agreement drafts and individual proposals can be reviewed through transaction-specific links without customer accounts. Document bytes use a private local store by default or an S3-compatible bucket when configured.

## Requirements

- Node.js 20.19+ or 22.12+ and npm
- Python 3.11+

## Run locally

From the repository root:

```powershell
npm.cmd install
python -m venv .venv
.venv\Scripts\python -m pip install -r services/api/requirements.txt
```

On macOS/Linux, use `npm` and `.venv/bin/python` instead. Run the API in one terminal:

```powershell
cd services/api
..\..\.venv\Scripts\python -m alembic upgrade head
$env:DEVELOPMENT_VERIFICATION='true' # local prototype only; never use for production
..\..\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run the web app in another terminal from the repository root:

```powershell
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. Create a business owner account, add a customer, and save a credit transaction. In Agreements, create a draft from that transaction, review or revise the full text, then create a review link and share it manually. The intended counterparty opens the link, reads the exact version, and can request a correction, reject, or explicitly accept after entering a code. The business dashboard refreshes agreement status about every 15 seconds. The old `/review/demo` page remains an illustrative sample; live invitations open `/review/invite#token=…`.

In Document Vault, owners and authorised staff can upload PDFs, PNGs, and JPEGs up to 10 MB, search by title or filename, filter by category, preview, download, and inspect prior versions. A confirmed agreement is automatically preserved as an immutable UTF-8 text file; existing confirmed agreements can be opened through the **Open preserved copy in Vault** button. Agreement PDFs are not generated yet.

In Payments, select a transaction to record partial payments, attach an existing Vault document, and mark a report acknowledged or disputed with a reason. The displayed outstanding balance includes the initial reported paid amount and later non-disputed payment records. Disputed amounts are shown separately and excluded until acknowledged. Negotiations records extension, instalment, correction, settlement, and revised-obligation proposals; Disputes records payment disagreements and resolutions. Each action adds history. A business-recorded accepted extension changes the **working deadline** while retaining the original transaction and confirmed agreement deadline. An accepted settlement proposal does not write down the debt or process a payment.

Phase 5 business-entered payments and outcomes remain **business-recorded, not independently verified customer responses**. Phase 6 adds an optional counterparty review link for individual proposals. Staff need the explicit **Manage obligations** permission to write records or send links; transaction viewers can read them. Do not treat a business-recorded acceptance or acknowledgment as a customer signature or proof of payment.

**Phase 6:** The new-transaction form can save one draft per signed-in user and business in IndexedDB. An offline submission is queued on that device; **Retry save** sends it after reconnecting. A stable UUID makes retries idempotent on the API. Server rejections leave the draft for review. Signing out clears that user's local drafts. Drafts contain business details on the device and are not encrypted at rest, so use a trusted device. The page must remain open for offline editing; after an offline reload, sign-in and draft restoration require connectivity. Files and authenticated API responses are never cached for offline use.

The same form offers browser speech recognition where supported, or typed transcript entry. It extracts tentative amounts and an ISO deadline, flags missing or inconsistent fields, and fills the form **only when the user clicks Apply suggestions**. It never records audio or sends transcript data to the MyBizVault API. A browser's speech provider may process audio externally and may require connectivity; this is not guaranteed offline transcription. The user reviews and approves the transaction before saving.

An open negotiation proposal can now get a seven-day private review link. Reissuing revokes the prior link. The counterparty can request a correction or decline through the link; explicit acceptance requires a single-use code in the local development mode. The code is displayed to the link holder, so identity remains unverified. With development verification off, acceptance is disabled until independent code delivery is connected. A response updates the proposal status and history, but never rewrites the original agreement or processes payment. Business users can also record an outcome themselves; its source is shown separately from a link response.

Optional delivery uses SMTP for email and a configured HTTPS SMS webhook. Only an explicit **Send email link** or **Send SMS link** action sends a message. Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` or `SMS_WEBHOOK_URL` and `SMS_WEBHOOK_TOKEN` as server environment secrets. The SMS webhook receives JSON `{"to":"...","message":"..."}` with a bearer token; adapt it to a chosen provider before production. Failed delivery returns a link for manual sharing. No provider credentials are included in this repository, and no real messages were sent in testing. See [Phase 6 integration notes](docs/phase6-integrations.md).

The transaction facts above the draft's **Proposed terms** heading stay linked to the saved transaction and cannot be edited in the agreement. This prevents a confirmed agreement from silently disagreeing with the dashboard's amount and deadline. Corrections to those core facts require a new transaction record in this prototype; the original record is preserved.

**Development verification:** with `DEVELOPMENT_VERIFICATION=true`, the code is shown to whoever holds the link. It is short-lived and single-use but **does not prove the person's identity or control of a phone or email channel**. It is not a legally sufficient signature. With the setting off (the default), acceptance is unavailable until independent code delivery is implemented; correction and rejection through the link still work and are marked as unverified. No SMS or email is sent by this prototype. Do not deploy with development verification enabled.

## Database configuration

The API reads `DATABASE_URL` from the environment or `services/api/.env`; its default is `sqlite:///./mybizvault.db` relative to the API working directory. SQLite is for local development. Production will use PostgreSQL through SQLAlchemy with a `postgresql+psycopg://...` URL. Run Alembic from `services/api`; `alembic upgrade head` applies all migrations. Set `FRONTEND_ORIGIN` to the actual web origin and `COOKIE_SECURE=true` behind HTTPS in a production environment. The web and API must be served from the same origin or through a trusted reverse proxy so session cookies and CSRF protection work. PostgreSQL integration tests and deployment hardening are still required before production.

The Phase 3 migration adds agreement, version, invitation, challenge, confirmation-event and audit tables plus a staff agreement permission. Existing Phase 2 business records remain in place. A downgrade to `0002_business_transactions` drops **all Phase 3 agreement data**; back up the database before any rollback and do not downgrade a populated database unless that data loss is explicitly intended.

The Phase 4 migration adds document metadata, immutable versions, event history, and separate staff view/manage permissions. The default private file directory is `services/api/vault_objects` when the API runs from `services/api`; it is ignored by Git. Set `STORAGE_BACKEND=s3`, `S3_BUCKET`, `S3_REGION`, and optionally `S3_ENDPOINT_URL` for an S3-compatible private bucket. Credentials use the standard AWS SDK credential chain. Do not make the bucket public; the API checks membership and verifies SHA-256 before serving file bytes. Back up both the database and object store together. Downgrading to Phase 3 drops Vault metadata and permissions, while stored objects need separate cleanup.

The Phase 5 migration adds payment, proposal, and append-only activity tables plus a staff obligation permission. Phase 6 adds a nullable transaction request ID and proposal invitation, code, and response tables. Existing transaction amounts and agreement content are not rewritten. Downgrading to Phase 5 drops proposal invitation history and removes retry IDs; back up the database first and do not downgrade a populated database unless that loss is intended. Live writes should be paused during a schema migration.

## Checks

```powershell
npm.cmd run typecheck
npm.cmd run build
cd services/api
python -m alembic upgrade head
python -m pytest -q
```

## Scope and architecture

See [docs/architecture.md](docs/architecture.md) for ownership and lifecycle decisions. The interface uses React Router for business routes and a separate public review route, TanStack Query and Axios for API data, React Hook Form and Zod for transaction forms, Tailwind CSS v4 with a shadcn-style Button primitive, and a web manifest. The API stores only hashes of random session and invitation tokens. Agreement content is preserved per version with a SHA-256 digest; sent links bind to an exact transaction, counterparty and version. Material edits create new versions and revoke old links. The server enforces transitions and stores confirmation and audit events. Staff need an explicit agreement-management permission.

No customer accounts or customer dashboard exist. Initial and later paid amounts are business-reported values, not independently verified payment events. PDF generation, payment processing, background offline sync, offline document access, on-device speech transcription, and USSD service operation are out of scope. Additional legal templates await reviewed content and rules. Email ownership is not verified, staff receive an owner-set initial password through an out-of-band channel, and password recovery is not yet available. Production requires independently delivered OTPs, distributed rate limiting, PostgreSQL concurrency and real S3 integration tests, operational secret management, delivery-provider validation, and legal review of electronic agreements in Uganda.
