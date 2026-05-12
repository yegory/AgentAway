from __future__ import annotations

import json
from pathlib import Path


def detect_test_command(repo_path: Path) -> list[str] | None:
    package_json = repo_path / "package.json"
    if package_json.exists():
        try:
            package = json.loads(package_json.read_text())
        except json.JSONDecodeError:
            package = {}
        if "test" in package.get("scripts", {}):
            return ["npm", "test", "--", "--watch=false"]

    if (repo_path / "pytest.ini").exists() or (repo_path / "pyproject.toml").exists() or (repo_path / "tests").exists():
        return ["python", "-m", "pytest"]

    if (repo_path / "go.mod").exists():
        return ["go", "test", "./..."]

    return None
