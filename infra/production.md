# Production

The first public target is Render.

## Services

- API web service: `apps/api/Dockerfile`
- Web service: `apps/web/Dockerfile`
- Worker background service: `apps/worker/Dockerfile`
- Render Postgres
- Render Key Value / Redis-compatible instance

## Required Environment

Set shared values on API and worker:

```bash
APP_ENV=production
DATABASE_URL=
REDIS_URL=
API_BASE_URL=
WEB_BASE_URL=
APP_ENCRYPTION_KEY=
APP_ACCESS_TOKEN_SECRET=
ACCESS_TOKEN_MINUTES=15
REFRESH_TOKEN_DAYS=30
API_RATE_LIMIT_PER_MINUTE=60
GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY_BASE64=
GITHUB_WEBHOOK_SECRET=
```

Set API-only Clerk values:

```bash
CLERK_ISSUER=
CLERK_JWKS_URL=
CLERK_AUTHORIZED_PARTIES=
```

Set web values:

```bash
NEXT_PUBLIC_API_BASE_URL=
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
NEXT_PUBLIC_GITHUB_APP_SLUG=
```

## Notes

Render provides `PORT`; the API and web Dockerfiles bind to it. The worker does not expose a port and should be deployed as a background worker.
