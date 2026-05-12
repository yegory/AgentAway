# Authentication

AgentAway uses a layered model: Clerk owns human identity, while AgentAway issues scoped API tokens for external clients that need to call the workbench API.

## Human Sign-In

Recommended Clerk configuration:

- Email/password for familiar account access.
- Email verification code and email link for passwordless recovery-friendly access.
- GitHub OAuth and Google OAuth for social/OIDC sign-in.
- Passkeys for phishing-resistant WebAuthn sign-in.
- Authenticator app TOTP and backup codes for MFA.

SMS is intentionally omitted because it usually requires paid provider capacity, adds SIM-swap risk, and is not needed for the public MVP showcase.

## Method Comparison

| Method | Strength | Tradeoff |
| --- | --- | --- |
| Password | Universal and easy to understand | Needs MFA and breach monitoring |
| Email code/link | Passwordless and low-friction | Email inbox becomes the security boundary |
| OAuth/OIDC | Delegates auth to GitHub/Google | Provider account health matters |
| Passkeys/WebAuthn | Phishing-resistant public-key auth | Browser/device support and recovery UX matter |
| TOTP MFA | Works across authenticator apps | Users must protect recovery codes |
| API access token | Good for scripts and integrations | Must be scoped, revocable, and short-lived |
| Refresh token | Enables longer-lived clients | Must rotate and detect reuse |
| M2M token | Good for service-to-service auth | Usually belongs to backend infrastructure, not end-user API access |

## AgentAway API Tokens

AgentAway API clients call `/api/auth/tokens` from a Clerk-authenticated browser session to create a token family. The response reveals the access token and refresh token once.

- Access tokens are signed JWTs with a short default lifetime of 15 minutes.
- Refresh tokens are opaque values stored only as HMAC-SHA256 hashes.
- Refresh tokens are one-time-use and rotate on every refresh.
- Reusing an old refresh token revokes the entire token family.
- Token grants carry explicit scopes: `account:read`, `repos:read`, `issues:read`, `issues:write`, `commands:write`, `runs:read`, and `runs:write`.
- External API clients use `/api/v1/*`; provider-key and GitHub-installation setup remains browser-session only.

## Security Controls

- Provider keys are encrypted with `APP_ENCRYPTION_KEY` and never returned raw.
- GitHub webhooks require `X-Hub-Signature-256` HMAC verification.
- GitHub writes use short-lived installation tokens and open draft PRs only.
- Sensitive actions write durable audit events.
- Token creation, refresh, revoke, and high-risk commands are rate-limited through Redis.
- Production startup requires Clerk verification config, webhook secret, encryption key, and access-token signing secret.
