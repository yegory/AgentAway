from dataclasses import dataclass, field
import re
from typing import Any


SUPPORTED_COMMANDS = {
    "plan",
    "fixplan",
    "fix",
    "proceed",
    "approve",
    "reject",
    "stop",
    "retry-tests",
    "explain",
    "make-smaller",
    "tests-only",
}

SHORT_COMMANDS = {"plan", "fixplan", "fix", "proceed"}

DEFAULT_FORBIDDEN_PATHS = [
    ".github/workflows/**",
    ".env*",
    "**/*.pem",
    "**/*.key",
    "**/id_rsa",
    "**/secrets/**",
    "infra/production/**",
]


@dataclass(frozen=True)
class ParsedCommand:
    command: str
    raw_text: str
    modifiers: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "modifiers": self.modifiers,
            "raw_text": self.raw_text,
        }


def parse_agent_command(text: str | None) -> ParsedCommand | None:
    if not text:
        return None

    stripped = text.strip()
    match = re.match(r"^/(?:agent(?:\s+([a-z][a-z-]*))?|([a-z][a-z-]*))(?:\b|$)", stripped, flags=re.IGNORECASE)
    if not match:
        return None

    if not match.group(1) and not match.group(2) and stripped[len("/agent") :].strip():
        return None

    command = (match.group(1) or match.group(2) or "plan").lower()
    if match.group(2) and command not in SHORT_COMMANDS:
        return None
    if command not in SUPPORTED_COMMANDS:
        return None

    lower_text = stripped.lower()
    modifiers: dict[str, Any] = {
        "forbidden_paths": DEFAULT_FORBIDDEN_PATHS,
        "tests_required": command in {"fix", "tests-only"} or "add tests" in lower_text,
    }

    if "only touch frontend" in lower_text or "frontend files" in lower_text:
        modifiers["allowed_paths"] = ["apps/web/**"]

    max_files_match = re.search(r"max(?:imum)?\s+(\d+)\s+files?", lower_text)
    if max_files_match:
        modifiers["max_files"] = int(max_files_match.group(1))

    return ParsedCommand(command=command, raw_text=stripped, modifiers=modifiers)
