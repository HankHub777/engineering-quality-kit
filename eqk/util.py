"""Small helpers: filesystem walk, git queries, tool lookup, redaction."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

# Directories never scanned: VCS, environments, caches, eqk's own output.
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".quality",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".tox",
    ".next",
}
MAX_FILES = 50_000


def walk_files(root: Path) -> list[str]:
    """Relative POSIX paths of files under root, skipping SKIP_DIRS and hidden dirs (except .github)."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and (not d.startswith(".") or d == ".github"))
        for name in filenames:
            out.append(Path(dirpath, name).relative_to(root).as_posix())
            if len(out) >= MAX_FILES:
                return out
    return out


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> tuple[int, str]:
    try:
        p = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""
    return p.returncode, p.stdout.strip()


def git_state(root: Path) -> dict:
    code, inside = git(root, "rev-parse", "--is-inside-work-tree")
    if code != 0 or inside != "true":
        return {"is_repo": False, "commit": None, "dirty": None}
    code, head = git(root, "rev-parse", "HEAD")
    _, status = git(root, "status", "--porcelain")
    return {"is_repo": True, "commit": head if code == 0 else None, "dirty": bool(status)}


def project_id(root: Path) -> str:
    """Stable, non-identifying id: hash of the root commit, else of the directory name."""
    code, roots = git(root, "rev-list", "--max-parents=0", "HEAD")
    seed = roots.splitlines()[0] if code == 0 and roots else "dir:" + root.resolve().name
    return "proj-" + hashlib.sha256(seed.encode()).hexdigest()[:12]


_REPO_TOOL_DIRS = (
    (".venv/bin", "repo-venv"),
    (".venv/Scripts", "repo-venv"),
    ("venv/bin", "repo-venv"),
    ("venv/Scripts", "repo-venv"),
    ("node_modules/.bin", "repo-node_modules"),
)


def resolve_tool(name: str, root: Path) -> tuple[str | None, str | None]:
    """Find a tool: repo-local environments first, then PATH. Never installs anything."""
    for sub, label in _REPO_TOOL_DIRS:
        d = root / sub
        if d.is_dir():
            found = shutil.which(name, path=str(d))
            if found:
                return found, label
    found = shutil.which(name)
    return (found, "PATH") if found else (None, None)


_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|passw(?:or)?d|authorization)(\s*[:=]\s*|\s+)(\S+)"
)
_TOKEN_SHAPES = re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})\b")


def redact(text: str, root: Path) -> str:
    """Strip local paths and obvious credentials before anything is written to a report."""
    for p in {str(root), str(root.resolve())}:
        text = text.replace(p, "<repo>")
    home = str(Path.home())
    if home and home != "/":
        text = text.replace(home, "~")
    text = _SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>", text)
    return _TOKEN_SHAPES.sub("<redacted>", text)
