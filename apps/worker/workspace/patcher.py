from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any


def write_generated_files(repo_path: Path, files: list[dict[str, Any]]) -> list[str]:
    written: list[str] = []
    for file_spec in files:
        relative_path = str(PurePosixPath(str(file_spec["path"])))
        target = repo_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        content = str(file_spec.get("content") or "")
        target.write_text(content, encoding="utf-8")
        written.append(relative_path)
    return written
