from __future__ import annotations

import os


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


APP_ENV = env("APP_ENV", "development")
DATABASE_URL = env("DATABASE_URL", "postgresql+psycopg://postgres:postgres@postgres:5432/pocket_maintainer")
API_BASE_URL = env("API_BASE_URL", "http://localhost:8000")
WEB_BASE_URL = env("WEB_BASE_URL", "http://localhost:3000")
WORKSPACE_ROOT = env("WORKSPACE_ROOT", "/tmp/pocket-maintainer-workspaces")
APP_ENCRYPTION_KEY = env("APP_ENCRYPTION_KEY")
GITHUB_APP_ID = env("GITHUB_APP_ID")
GITHUB_APP_PRIVATE_KEY_BASE64 = env("GITHUB_APP_PRIVATE_KEY_BASE64")
DEFAULT_OPENAI_MODEL = env("DEFAULT_OPENAI_MODEL", "gpt-4.1-mini")
DEFAULT_ANTHROPIC_MODEL = env("DEFAULT_ANTHROPIC_MODEL", "claude-sonnet-4-5")
DEFAULT_DEEPSEEK_MODEL = env("DEFAULT_DEEPSEEK_MODEL", "deepseek-v4-flash")
