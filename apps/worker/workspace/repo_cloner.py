from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def clone_repository(clone_url: str, destination: Path, default_branch: str) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", default_branch, clone_url, str(destination)],
        text=True,
        capture_output=True,
        timeout=120,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "no output").strip()
        raise RuntimeError(f"git clone failed for default branch '{default_branch}': {detail}")


def git(repo_path: Path, *args: str, timeout_seconds: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_path,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=True,
    )
