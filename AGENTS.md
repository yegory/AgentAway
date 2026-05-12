# AgentAway CodeMap

Purpose: Pocket Maintainer MVP, implemented incrementally. Current scope is Public GitHub Agent V1: Clerk-compatible account auth, GitHub App installation linking, encrypted BYOK provider keys, `/plan` and `/fixplan` GitHub comments, `/proceed`, and `/fix` draft-PR attempts.

## Context Rules

- Start here, then use `rg --files` before opening code.
- Prefer reading one contract file plus one caller over scanning whole folders.
- Ignore generated/heavy paths: `node_modules`, `.next`, `__pycache__`, `.pytest_cache`, `.venv`, Docker volumes.
- Keep agent powers conservative: never merge, never push to the default branch, and keep policy checks before writing generated files.
- Keep edits boring and local: API code in `apps/api`, worker code in `apps/worker`, web code in `apps/web`.

## CodeMap

```text
docker-compose.yml
  local system graph: postgres + redis -> api + worker -> web

apps/api/
  Dockerfile, requirements.txt
    FastAPI runtime image.
  app/config.py
    Env contract. Reads DATABASE_URL, REDIS_URL, API/WEB URLs, Clerk, GitHub App, encryption, API token, rate-limit, and provider defaults.
  app/db.py
    Engine/session setup, `create_tables()`, compatibility column additions, `check_postgres()`, `check_redis()`.
  app/celery_app.py
    API-side Celery client. Sends named tasks to Redis broker/backend.
  app/main.py
    FastAPI app. Routes:
      GET  /health       -> Postgres + Redis readiness
      POST /tasks/ping   -> enqueue worker smoke task
      GET  /tasks/{id}   -> inspect smoke task result
      POST /webhooks/github -> verify, dedupe, persist, enqueue
      GET  /api/me       -> current account
      GET/POST/DELETE /api/provider-keys -> encrypted BYOK setup
      GET  /api/installations -> linked GitHub App installs
      POST /api/github/installations/link -> link install callback
      GET  /api/runs     -> user-scoped run inbox
      GET/POST/DELETE /api/auth/tokens -> scoped API token grants
      POST /api/auth/refresh|revoke -> refresh-token rotation and family revocation
      GET  /api/auth/audit -> user audit events
      /api/v1/* -> scoped external API for workbench actions
  app/routes/webhooks.py
    Raw-body HMAC verification. Creates `WebhookEvent`; creates user-scoped `AgentRun` for `/plan|fixplan|proceed|fix`; enqueues plan/fix tasks.
  app/routes/runs.py
    Auth-scoped run list/detail.
  app/routes/provider_keys.py, app/routes/github.py, app/routes/auth.py
    Account setup APIs.
  app/routes/auth_tokens.py, app/routes/api_v1.py
    API token lifecycle and scoped external workbench API.
  app/services/command_parser.py
    Small deterministic parser.
  app/services/auth.py, api_tokens.py, audit_log.py, rate_limits.py, crypto.py, providers.py, policy_engine.py
    Clerk token validation, first-party API tokens, durable audits, Redis rate limits, encrypted key handling, provider metadata, and safety checks.
  app/models.py
    SQLAlchemy tables: UserAccount, ApiTokenGrant, ApiRefreshToken, ProviderCredential, GitHubInstallation, Repository, RepositoryAccess, WebhookEvent, AgentRun, RunEvent, AuditLog.

apps/worker/
  Dockerfile, requirements.txt
    Celery worker runtime image.
  worker.py
    Celery app configured from REDIS_URL.
  tasks/health.py
    `pocket_maintainer.health.ping`: proves worker execution.
  tasks/handle_webhook.py
    `pocket_maintainer.webhooks.handle`: marks stored events processed.
  tasks/create_plan.py
    `pocket_maintainer.runs.create_plan`: generates a structured plan and comments it back to GitHub.
  tasks/implement_patch.py
    `pocket_maintainer.runs.implement_patch`: clones, branches, writes model-generated files, runs detected tests, pushes, opens a draft PR.
  services/{github_app,model_provider,crypto,db,policy,run_helpers}.py
    Worker-side GitHub App auth, provider calls, DB updates, and policy helpers.
  workspace/{repo_cloner,patcher,test_detector,docker_runner}.py
    Git clone/branch helpers, generated file writer, test command detection, bounded command runner.

apps/web/
  Dockerfile, package.json, next.config.ts, tsconfig.json
    Next.js app shell.
  app/page.tsx
    Setup shell with API status, provider keys, GitHub App installs.
  app/runs/page.tsx
    Read-only run inbox shell.
  app/runs/[runId]/page.tsx
    Run detail shell.
  components/SystemStatus.tsx
    Client-side `/health` probe.
  components/RunList.tsx, RunDetailClient.tsx
    Client-side run inbox/detail readers.
  components/ProviderKeys.tsx, Installations.tsx, GitHubInstallCallback.tsx, AuthActions.tsx
    Account setup UI.
  components/SecurityCenter.tsx
    Clerk account security, scoped API token UI, audit events, and connection posture.
  components/{RunCard,PlanCard,DiffSummary,TestResults,MobileActionBar}.tsx
    Placeholder exports for later UI milestones.
  lib/api.ts
    Browser API base URL helper.
  lib/api.ts
    Browser API base URL and authenticated fetch helper.

packages/shared/
  Placeholder for shared schemas/constants after contracts stabilize.

infra/
  GitHub App, production, and security setup notes.
```

## Contracts

- API health response: `{"status":"ok","dependencies":{"postgres":"ok","redis":"ok"}}`
- Worker smoke task name: `pocket_maintainer.health.ping`
- Webhook task name: `pocket_maintainer.webhooks.handle`
- Plan task name: `pocket_maintainer.runs.create_plan`
- Fix task name: `pocket_maintainer.runs.implement_patch`
- Commands: `/plan`, `/fixplan`, `/proceed`, `/fix`; `/agent ...` remains supported.
- Webhook route requires `GITHUB_WEBHOOK_SECRET` and `X-Hub-Signature-256`.
- Duplicate delivery IDs return 202 with `"status":"duplicate"` and do not create new runs.
- Production `/api/*` routes require Clerk JWTs; local dev falls back to `dev-user` when Clerk is unconfigured.
- Provider keys are encrypted with `APP_ENCRYPTION_KEY` and never returned raw.
- API access tokens are short-lived JWTs signed by `APP_ACCESS_TOKEN_SECRET`; refresh tokens are opaque, hashed at rest, one-time-use, rotated, and family-revoked on reuse.
- External API scopes: `account:read`, `repos:read`, `issues:read`, `issues:write`, `commands:write`, `runs:read`, `runs:write`.
- Local URLs: web `http://localhost:3000`, API `http://localhost:8000`

## Commands

```bash
cp .env.example .env
docker compose up --build
curl http://localhost:8000/health
curl -X POST http://localhost:8000/tasks/ping
curl http://localhost:8000/tasks/<task_id>
```
