# GitHub App Setup

Create one GitHub App for production and point it at the public API.

## Webhook

- Payload URL: `${API_BASE_URL}/webhooks/github`
- Content type: `application/json`
- Secret: same value as `GITHUB_WEBHOOK_SECRET`
- SSL verification: enabled

For local testing, expose the API:

```bash
cloudflared tunnel --url http://localhost:8000
```

Then temporarily use:

```text
https://<trycloudflare-host>/webhooks/github
```

## Permissions

- Metadata: read
- Contents: read/write
- Issues: read/write
- Pull requests: read/write

## Events

Subscribe to:

- Issues
- Issue comments
- Installation
- Installation repositories

## Environment

Download the GitHub App private key, base64 encode the PEM, and set:

```bash
GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY_BASE64=
GITHUB_APP_SLUG=
GITHUB_WEBHOOK_SECRET=
```

Set the app's setup/callback URL to:

```text
${WEB_BASE_URL}/github/callback
```
