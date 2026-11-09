"""Profile loading. Profiles are data (JSON), not code, so they can be reviewed and diffed."""

from __future__ import annotations

import json
from pathlib import Path

PROFILE_DIR = Path(__file__).parent / "profiles"
TEMPLATE_DIR = Path(__file__).parent / "templates"


def list_ids() -> list[str]:
    return sorted(p.stem for p in PROFILE_DIR.glob("*.json"))


def _raw(profile_id: str) -> dict:
    path = PROFILE_DIR / f"{profile_id}.json"
    if not path.is_file():
        raise KeyError(f"unknown profile {profile_id!r}; available: {', '.join(list_ids())}")
    return json.loads(path.read_text(encoding="utf-8"))


def load(profile_id: str) -> dict:
    """Resolve `extends` (single parent). Child checks with the same id replace parent checks."""
    prof = _raw(profile_id)
    parent_id = prof.get("extends")
    if not parent_id:
        return prof
    parent = load(parent_id)
    child_ids = {c["id"] for c in prof["checks"]}
    merged = dict(prof)
    merged["checks"] = [c for c in parent["checks"] if c["id"] not in child_ids] + prof["checks"]
    merged["scaffold"] = parent.get("scaffold", []) + prof.get("scaffold", [])
    return merged


def template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")
