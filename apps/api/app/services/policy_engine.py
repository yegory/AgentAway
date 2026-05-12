from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import PurePosixPath

from app.services.command_parser import DEFAULT_FORBIDDEN_PATHS


AUTHORIZED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
AUTHORIZED_PERMISSIONS = {"admin", "maintain", "write"}


@dataclass(frozen=True)
class PolicyResult:
    allowed: bool
    reason: str = ""


def author_association_is_allowed(association: str | None) -> bool:
    return (association or "").upper() in AUTHORIZED_ASSOCIATIONS


def repo_permission_is_allowed(permission: str | None) -> bool:
    return (permission or "").lower() in AUTHORIZED_PERMISSIONS


def path_is_forbidden(path: str, forbidden_paths: list[str] | None = None) -> bool:
    forbidden_paths = forbidden_paths or DEFAULT_FORBIDDEN_PATHS
    normalized = str(PurePosixPath(path))
    if normalized.startswith("../") or normalized.startswith("/") or normalized == ".":
        return True

    return any(fnmatch(normalized, pattern) for pattern in forbidden_paths)


def validate_file_plan(
    paths: list[str],
    max_files: int | None = None,
    forbidden_paths: list[str] | None = None,
) -> PolicyResult:
    if max_files is not None and len(paths) > max_files:
        return PolicyResult(False, f"Requested {len(paths)} files, above max_files={max_files}.")

    for path in paths:
        if path_is_forbidden(path, forbidden_paths=forbidden_paths):
            return PolicyResult(False, f"Path is not allowed: {path}")

    return PolicyResult(True)
