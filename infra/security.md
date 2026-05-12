# Security

## Auth

Production API routes under `/api/*` require a Clerk session token. `/health` and `/webhooks/github` remain public because GitHub webhooks authenticate with HMAC signatures.

Local development can run without Clerk; the API creates a `dev-user` account when `APP_ENV=development` and Clerk is not configured.

External clients use AgentAway API tokens on `/api/v1/*`. Access tokens are short-lived JWTs, refresh tokens are opaque one-time-use values stored only as hashes, and refresh-token reuse revokes the whole token family.

## Provider Keys

Provider API keys are bring-your-own-key and are only accepted by the FastAPI backend. They are encrypted with `APP_ENCRYPTION_KEY` before storage and are never returned to the browser. UI responses only include masked key hints.

Use a high-entropy Fernet key for production:

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

## API Token Secret

Set `APP_ACCESS_TOKEN_SECRET` to a separate high-entropy value in production. It signs AgentAway access JWTs and HMACs refresh-token hashes.

```bash
python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

## Audit And Rate Limits

Security-sensitive actions write `audit_logs` rows, including API token lifecycle events, provider-key changes, GitHub installation linking, command posting, and run stop requests. Token lifecycle and high-risk command endpoints use Redis-backed rate limits.

## GitHub Actions

AgentAway acts through short-lived GitHub App installation tokens. The app can create branches, comments, and draft pull requests, but the worker never merges and never pushes to the default branch.

The worker rejects forbidden paths such as `.env*`, keys, PEM files, workflow files, and configured secrets paths.
