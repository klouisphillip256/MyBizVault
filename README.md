# MyBizVault

MyBizVault records business transactions, customer payment reports, versioned credit agreements, responses, and private documents. React/Vite lives in `apps/web`; FastAPI and Alembic live in `services/api`.

## Local development

Requirements: Node.js 20.19+ and Python 3.11+.

```powershell
npm.cmd install
python -m pip install -r services/api/requirements.txt
cd services/api
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In a second terminal from the repository root:

```powershell
npm.cmd run dev
```

Open http://127.0.0.1:5173. Vite forwards `/api` to port 8000. SQLite and local Vault files are for development only. Set `DEVELOPMENT_VERIFICATION=true` locally only to exercise acceptance without a provider. The code appears to anyone holding the link and does not establish identity.

## Product flow

Create a business and customer, then enter a cash or credit transaction. The form supports optional itemized lines, inline customer creation, local offline drafts, and voice assisted suggestions. A reported payment creates a receipt; an outstanding balance creates an agreement draft. Later payments create separate receipts. Historical transactions remain available with payment, approval, document, and communication history.

Agreement documents extend the existing commercial format with party contacts, itemized amounts, obligations, and relevant Uganda legal context. Versions retain SHA-256 digests. Owners or staff with agreement permission can preview, download, and share PDFs. Receipts are immutable snapshots of reported payment details. MyBizVault does not independently verify funds.

Review links bind to a customer, transaction, and version. A customer can request correction or reject from the link. Acceptance requires explicit confirmation of the displayed version and a one time code requested through the page. With Brevo or Africa's Talking configured, an explicit customer action sends the code. The Africa's Talking sandbox also supports a reference and PIN based USSD response. These records document observed actions; they do not guarantee legal identity or enforceability.

Optional email, SMS, and WhatsApp messages require an explicit send action. Logs distinguish simulated, submitted, delivered, and failed states. Provider acceptance is not proof of delivery. Manual WhatsApp sharing is available without Meta credentials.

## Deployment and checks

See [Vercel and Neon deployment](docs/deployment.md). The deployed app uses PostgreSQL and database backed private object storage; no persistent function filesystem or background worker is required.

```powershell
npm.cmd run typecheck
npm.cmd run build
cd services/api
python -m pytest -q
python -m alembic upgrade head
```

The API defaults to SQLite when `DATABASE_URL` is absent. Do not use SQLite on Vercel. Keep provider credentials in backend environment secrets, never in frontend variables or Git. Use fictional demonstration data until provider, backup, and legal review are complete.
