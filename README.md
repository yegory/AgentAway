# Pocket Maintainer

Pocket Maintainer is a mobile-first GitHub App for supervised coding-agent runs. This repository is now moving into **Public GitHub Agent V1**.

The phone-facing product is a decision interface: approve plans, stop runs, review summaries, and link out to GitHub. Server-side workers will do the heavy code work in later milestones.

## What Is Implemented

- Monorepo skeleton
- Docker Compose for Postgres, Redis, FastAPI, Celery, and Next.js
- FastAPI `/health` endpoint that checks Postgres and Redis
- API endpoints to enqueue and inspect a Celery smoke task
- Celery worker with a `pocket_maintainer.health.ping` task
- Next.js app shell with API health status, run inbox, run details, provider-key setup, and GitHub App setup
- `.env.example`
- `AGENTS.md` with a compact CodeMap for future implementation passes
- GitHub webhook route at `POST /webhooks/github`
- HMAC SHA-256 verification using `X-Hub-Signature-256`
- Delivery deduplication using `X-GitHub-Delivery`
- Webhook event persistence
- `/agent` issue comment parsing with short aliases like `/plan`
- Clerk-compatible protected API routes with local dev fallback
- AgentAway API access/refresh tokens with scopes, rotation, reuse detection, revocation, audit logs, and `/api/v1/*` routes
- Encrypted BYOK provider credentials for OpenAI, Anthropic, and DeepSeek
- GitHub App installation linking and repository sync
- `AgentRun` creation for `/plan`, `/fixplan`, `/proceed`, and `/fix`
- `/agent plan` worker task that generates a plan and comments it back to GitHub
- `/agent fixplan` worker path that revises the latest completed plan
- `/agent proceed` worker path that implements the latest completed plan
- `/agent fix` worker task that clones, branches, writes generated files, runs detected tests, pushes, and opens a draft PR

The agent workflow is intentionally conservative: it never merges and never writes directly to the default branch.

## Installation

Prerequisites:

- Docker Desktop or another Docker Compose compatible runtime
- GitHub account with permission to create a GitHub App
- Clerk project if you want production auth
- Cloudflare account if you want to expose the local API/webhook during development

Start the app locally:

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/health

In local development, protected API routes use a dev account if Clerk is not configured. Production should set Clerk, GitHub App, and `APP_ENCRYPTION_KEY` values.

Useful Docker commands:

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f web
docker compose down
docker compose down --volumes
```

Run the checks locally:

```bash
cd apps/api
python -m unittest discover app/tests

cd ../web
npm test
npm run build
```

If your system Node.js is older than the version required by Next.js, use Node 20 or newer.

## GitHub App Setup

Create a GitHub App from GitHub Developer Settings. For local development, set the webhook URL to your public API URL plus `/webhooks/github`; for production, use the deployed API URL. Use a long random webhook secret and put the same value in `GITHUB_WEBHOOK_SECRET`.

Required GitHub App permissions:

- Metadata: read
- Contents: read/write
- Issues: read/write
- Pull requests: read/write

Webhook events:

- Issues
- Issue comments
- Installation
- Installation repositories

After creating the app, generate a private key. GitHub downloads it as a `.pem` file. Do not commit that file. Convert it to a single-line base64 value for `.env`:

```bash
base64 -i path/to/github-app-private-key.pem | tr -d '\n'
```

Use that output as `GITHUB_APP_PRIVATE_KEY_BASE64`. The `.gitignore` and `.dockerignore` files intentionally ignore `.env`, `.pem`, and common private-key file formats.

## Cloudflare For Local Webhooks

Cloudflare Tunnel is a convenient way to receive real GitHub webhooks while running Docker locally. Start the app with Docker Compose, then expose the API port:

```bash
cloudflared tunnel --url http://localhost:8000
```

Use the generated HTTPS URL as the GitHub App webhook base, for example `https://your-tunnel.trycloudflare.com/webhooks/github`. If you deploy publicly, point Cloudflare DNS at the deployed web and API services instead and set `WEB_BASE_URL` and `API_BASE_URL` to those HTTPS URLs.

## Environment Variables

Copy `.env.example` to `.env` for local development. Keep `.env` private and never commit it.

Core service values:

```bash
APP_ENV=development
API_BASE_URL=http://localhost:8000
WEB_BASE_URL=http://localhost:3000
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/pocket_maintainer
REDIS_URL=redis://redis:6379/0
```

Security values:

```bash
APP_ENCRYPTION_KEY=<fernet-key>
APP_ACCESS_TOKEN_SECRET=<random-token-signing-secret>
ACCESS_TOKEN_MINUTES=15
REFRESH_TOKEN_DAYS=30
API_RATE_LIMIT_PER_MINUTE=60
```

Generate local secret material with:

```bash
python - <<'PY'
import secrets
from cryptography.fernet import Fernet
print("APP_ENCRYPTION_KEY=" + Fernet.generate_key().decode())
print("APP_ACCESS_TOKEN_SECRET=" + secrets.token_urlsafe(48))
PY
```

Clerk values:

```bash
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<clerk-publishable-key>
CLERK_SECRET_KEY=<clerk-secret-key>
CLERK_ISSUER=<clerk-issuer>
CLERK_JWKS_URL=<clerk-jwks-url>
CLERK_AUTHORIZED_PARTIES=https://your-web.example.com
```

If you are running the Next.js app directly instead of Docker, put the public and secret Clerk keys in `apps/web/.env.local`. When using Docker Compose, keep them in the repo-root `.env` file so Compose passes them to the web container. The FastAPI service does not need `CLERK_SECRET_KEY`; it verifies Clerk session JWTs through `CLERK_ISSUER` or `CLERK_JWKS_URL`.

For Docker Compose, `NEXT_PUBLIC_*` values are also passed as web build arguments because Next.js inlines public environment variables into the browser bundle. After changing Clerk or API public env values, rebuild the web image:

```bash
docker compose up --build web
```

GitHub App values:

```bash
GITHUB_APP_ID=<github-app-id>
GITHUB_APP_CLIENT_ID=<github-app-client-id>
GITHUB_APP_CLIENT_SECRET=<github-app-client-secret>
GITHUB_APP_PRIVATE_KEY_BASE64=<base64-pem>
GITHUB_APP_SLUG=<github-app-slug>
GITHUB_WEBHOOK_SECRET=<github-webhook-secret>
```

Model provider defaults:

```bash
DEFAULT_OPENAI_MODEL=gpt-4.1-mini
DEFAULT_ANTHROPIC_MODEL=claude-sonnet-4-5
DEFAULT_DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

## Public App Setup

Required production configuration:

```bash
APP_ENV=production
API_BASE_URL=https://your-api.example.com
WEB_BASE_URL=https://your-web.example.com
APP_ENCRYPTION_KEY=<fernet-key>
APP_ACCESS_TOKEN_SECRET=<random-token-signing-secret>
ACCESS_TOKEN_MINUTES=15
REFRESH_TOKEN_DAYS=30

NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<clerk-publishable-key>
CLERK_SECRET_KEY=<clerk-secret-key>
CLERK_ISSUER=<clerk-issuer>
CLERK_JWKS_URL=<clerk-jwks-url>
CLERK_AUTHORIZED_PARTIES=https://your-web.example.com

GITHUB_APP_ID=<github-app-id>
GITHUB_APP_PRIVATE_KEY_BASE64=<base64-pem>
GITHUB_APP_SLUG=<github-app-slug>
GITHUB_WEBHOOK_SECRET=<github-webhook-secret>
```

For a hosted deployment, run the API, worker, web app, Postgres, and Redis as separate services. The API and worker need database, Redis, GitHub App, encryption, and provider-related settings. The web service needs `NEXT_PUBLIC_API_BASE_URL` and Clerk publishable settings.

Users sign in, install the GitHub App, save an encrypted provider key, then trigger work with issue comments:

```text
/plan add tests max 2 files
/fixplan keep it to one source file and one test file
/proceed
/fix add tests max 2 files
```

External clients can create scoped API token families from the Security Center, then call `/api/v1/*` with short-lived access tokens and rotate refresh tokens through `/api/auth/refresh`. See `infra/authentication.md` for the auth-method comparison and token model.

## What You Can Do So Far

- Sign in with Clerk in production, or use local dev auth when Clerk is not configured.
- Link a GitHub App installation and sync repositories.
- Store BYOK provider keys encrypted server-side.
- Open the workbench, browse linked repositories and issues, and create GitHub issues.
- Post `/plan`, `/fixplan`, `/proceed`, and `/fix` commands from the web UI or GitHub comments.
- Generate plans, revise plans, attempt fixes, run detected tests, and open draft pull requests.
- Use the Security Center to create scoped API tokens, rotate refresh tokens, revoke token families, and inspect audit events.
- Call the external `/api/v1/*` API for scoped workbench actions.

## Verify GitHub Webhook Ingestion

Set a local webhook secret before starting Docker:

```bash
printf 'GITHUB_WEBHOOK_SECRET=%s\n' 'replace-with-a-local-test-value' >> .env
docker compose up --build
```

Send the fixture as a signed GitHub-style webhook:

```bash
BODY="$(cat tests/webhooks/issue_comment_plan.json)"
SIG="$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac 'dev-webhook-secret' -hex | awk '{print $2}')"

curl -i \
  -X POST http://localhost:8000/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issue_comment" \
  -H "X-GitHub-Delivery: local-delivery-1" \
  -H "X-Hub-Signature-256: sha256=$SIG" \
  --data "$BODY"
```

Inspect the created run:

```bash
curl http://localhost:8000/api/runs
```

Send the same delivery ID again to verify dedupe:

```bash
curl -i \
  -X POST http://localhost:8000/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issue_comment" \
  -H "X-GitHub-Delivery: local-delivery-1" \
  -H "X-Hub-Signature-256: sha256=$SIG" \
  --data "$BODY"
```

Expected response status is still `202`, with `"status":"duplicate"`.

## Verify the Worker Smoke Task

Enqueue a task:

```bash
curl -X POST http://localhost:8000/tasks/ping
```

Copy the returned `task_id`, then inspect it:

```bash
curl http://localhost:8000/tasks/<task_id>
```

Expected completed result:

```json
{
  "task_id": "...",
  "state": "SUCCESS",
  "result": {
    "status": "ok",
    "message": "pong"
  }
}
```

## Repository Layout

```text
apps/api      FastAPI service
apps/worker   Celery worker and future agent runtime
apps/web      Next.js app shell
packages      Shared schemas/constants later
infra         Deployment/security docs later
tests         Cross-service fixtures later
```

See `AGENTS.md` for the token-efficient CodeMap used by future implementation agents.
