from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import PurePosixPath


DEFAULT_FORBIDDEN_PATHS = [
    ".github/workflows/**",
    ".env*",
    "**/*.pem",
    "**/*.key",
    "**/id_rsa",
    "**/secrets/**",
    "infra/production/**",
]
AUTHORIZED_PERMISSIONS = {"admin", "maintain", "write"}


@dataclass(frozen=True)
class PolicyResult:
    allowed: bool
    reason: str = ""


def permission_allowed(permission: str | None) -> bool:
    return (permission or "").lower() in AUTHORIZED_PERMISSIONS


def path_forbidden(path: str, forbidden_paths: list[str] | None = None) -> bool:
    normalized = str(PurePosixPath(path))
    if normalized.startswith("/") or normalized.startswith("../") or normalized == ".":
        return True
    return any(fnmatch(normalized, pattern) for pattern in (forbidden_paths or DEFAULT_FORBIDDEN_PATHS))


def validate_paths(paths: list[str], max_files: int | None, forbidden_paths: list[str] | None = None) -> PolicyResult:
    if max_files is not None and len(paths) > max_files:
        return PolicyResult(False, f"Generated {len(paths)} files, above max_files={max_files}.")
    for path in paths:
        if path_forbidden(path, forbidden_paths):
            return PolicyResult(False, f"Generated path is not allowed: {path}")
    return PolicyResult(True)
