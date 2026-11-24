# Vercel and Neon deployment

The root `vercel.json` routes `/api/*` to FastAPI and all other paths to the Vite frontend in one Vercel project. The browser and API share an origin, preserving the existing session cookie and CSRF model. The frontend uses relative `/api` requests. The `apps/web/vercel.json` file provides SPA fallback if the frontend is deployed separately.

## Prerequisites

Create a Neon PostgreSQL database and keep its connection string private. Use a direct connection for Alembic migrations; the API may use a pooled URL. Back up a populated database before upgrading it. The schema must reach revision `0014_unique_initial_receipts`. Restore a tested backup to undo a release involving data; downgrading a populated schema may discard newer records.

Create a Vercel project from the private GitHub repository with the repository root as project root. The root `vercel.json` declares frontend (`apps/web`) and backend (`services/api`) services. The backend uses Python 3.13 and `app.main:app`. Confirm both services and the `/api/*` route in deployment output.

Set backend environment variables, replacing the domain with the actual Vercel domain:

```text
DATABASE_URL=postgresql://...NEON_CONNECTION...
FRONTEND_ORIGIN=https://YOUR-VERCEL-DOMAIN
COOKIE_SECURE=true
DEVELOPMENT_VERIFICATION=false
STORAGE_BACKEND=database
```

Database storage keeps private Vault bytes outside the serverless function filesystem. It is intended for the prototype's 10 MB per file limit; assess storage cost as usage grows. Session, invitation, and code state are database backed; no continuously running worker is needed.

Run migrations from `services/api` against Neon using an authorized machine or CI job with the same `DATABASE_URL` before opening the application:

```powershell
python -m alembic upgrade head
python -m alembic current
```

The migrations preserve old transaction rows and agreement version text. They do not copy data from local SQLite to Neon. If historical local data must appear publicly, transfer it before cutover and verify row counts, agreement hashes, and a historical document.

## Optional provider credentials

Set these only in the backend environment after the accounts and test assets exist:

```text
BREVO_API_KEY=...
BREVO_SENDER_EMAIL=verified-sender@example.com
BREVO_SENDER_NAME=MyBizVault
BREVO_WEBHOOK_TOKEN=long-random-secret
AT_API_KEY=...
AT_USERNAME=sandbox
AT_SANDBOX=true
AT_WEBHOOK_TOKEN=long-random-secret
USSD_CALLBACK_TOKEN=long-random-secret
WHATSAPP_ACCESS_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_TEST_MODE=true
META_APP_SECRET=...
META_VERIFY_TOKEN=long-random-secret
```

The owner only endpoint `/api/businesses/{business_id}/delivery/provider-tests` probes Brevo, Africa's Talking, and Meta credentials without sending messages. Status webhook endpoints are `/api/webhooks/brevo`, `/api/webhooks/africas-talking?token=AT_WEBHOOK_TOKEN`, and `/api/webhooks/meta`. Configure Brevo authorization as `Bearer BREVO_WEBHOOK_TOKEN`; Meta must sign requests with the app secret. The Africa's Talking sandbox USSD callback URL is `/api/ussd/callback?token=USSD_CALLBACK_TOKEN`. Protect the callback token in URLs and logs. Test with fictional customers in the sandbox simulator.

## Public verification

1. Check `https://YOUR-VERCEL-DOMAIN/api/health` returns a connected database.
2. Register a fictional owner and create fictional fully paid, unpaid, and partially paid transactions. Open their historical detail pages and PDF documents.
3. Record another payment. Check its new receipt and unchanged agreement version and original deadline.
4. Create a review link and verify a correction or rejection against the displayed version, plus duplicate response protection. With email or SMS configured, explicitly request a code and accept a fresh fictional agreement.
5. Upload, preview, and download a small fictional Vault file; check cross business access and sign out.

Do not declare deployment complete until these checks pass on the public URL. Creating a transaction or opening a review page sends no communication.
