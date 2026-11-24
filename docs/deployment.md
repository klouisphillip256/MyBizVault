# Trial hosting plan

Keep one private GitHub repository, with two deployable applications:

| Railway service | Source | Purpose |
| --- | --- | --- |
| `web` | Repository root, `Dockerfile.web` | React app served by Caddy; public HTTPS domain |
| `api` | `services/api`, its `Dockerfile` | FastAPI; private Railway network only |
| `Postgres` | Railway PostgreSQL template | Persistent relational data |
| Bucket | Railway private storage bucket | Vault file bytes |

The frontend proxies `/api/*` to `api.railway.internal:8000`. This preserves the browser's single origin, which the current session cookies and CSRF checks require. Name the API service exactly `api`; if the name differs, change the upstream in `apps/web/Caddyfile`. Expose only `web` to the public internet. Keep the database and bucket private.

## Railway setup

1. Connect the **private** GitHub repository to a new Railway project. Add PostgreSQL and a private bucket.
2. Add the `api` service from the same repository. Set its root directory to `/services/api`; Railway will use `services/api/Dockerfile`. Set `PORT=8000`. Do not generate a public domain for this service. The container applies Alembic migrations before starting; use one API replica for this prototype.
3. Set API variables using Railway's variable references, choosing the actual names shown by your Postgres and bucket services:

   ```text
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   FRONTEND_ORIGIN=https://YOUR-WEB-DOMAIN
   COOKIE_SECURE=true
   DEVELOPMENT_VERIFICATION=false
   STORAGE_BACKEND=s3
   S3_BUCKET=${{Bucket.BUCKET}}
   S3_ENDPOINT_URL=${{Bucket.ENDPOINT}}
   S3_REGION=${{Bucket.REGION}}
   AWS_ACCESS_KEY_ID=${{Bucket.ACCESS_KEY_ID}}
   AWS_SECRET_ACCESS_KEY=${{Bucket.SECRET_ACCESS_KEY}}
   ```

   The API accepts Railway's ordinary `postgresql://` URL and selects the installed psycopg v3 driver. Confirm the bucket variable names and endpoint shown in your Railway dashboard. Do not paste credentials into Git.
4. Add the `web` service from the same repository. Set root directory to `/` and Dockerfile path to `Dockerfile.web`; set `PORT=8080`. Generate a public domain. Put that exact `https://...` origin in the API's `FRONTEND_ORIGIN` and redeploy the API. The web and API services must be in the same Railway project/environment so private networking works.
5. Check `https://YOUR-WEB-DOMAIN/api/health`, registration/login, and a Vault upload/download. Test an invitation with `DEVELOPMENT_VERIFICATION=false`; acceptance will remain unavailable until independent verification is implemented.

Railway's new-account trial gives a one-time credit for 30 days. Its continuing Free plan has a smaller monthly usage allowance; the web, API, and Postgres may exceed it. Set a spend limit and review usage before the trial expires. Do not rely on a container filesystem or SQLite for deployed records. Back up both PostgreSQL and the bucket before trusting the service with real business documents.

Vercel Hobby is restricted to personal, non-commercial use. A Vercel Pro trial could host the frontend with an external rewrite to a public Railway API, but that adds a public API endpoint and a second provider to configure. Use the Railway setup above for the initial trial. Revisit hosting after verification, security, backup, and cost checks.
