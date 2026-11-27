"""`eqk verify`: run existing tools, record evidence, never report un-run checks as passed."""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from . import profiles as profiles_mod
from .adoption import CONFIG, QUALITY_DIR, check_applicability
from .inspection import detect
from .util import git_state, project_id, redact, resolve_tool

SCHEMA_VERSION = "0.1"
MAX_SUMMARY_LINES = 15
LOCATION_RE = re.compile(r"[\w./-]+\.\w+(:\d+(:\d+)?:|\(\d+,\d+\))")  # a.py:1:2:  /  a.ts(1,2)
ERROR_HINTS = ("error", "fail", "found", "✖", "×", "e:", "mismatch", "would reformat")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _summarize(output: str) -> list[str]:
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    located = [ln for ln in lines if LOCATION_RE.search(ln)]  # file:line findings first
    hits = [ln for ln in lines if any(h in ln.lower() for h in ERROR_HINTS)]
    chosen = (located + [h for h in hits if h not in located])[:MAX_SUMMARY_LINES] or lines[-MAX_SUMMARY_LINES:]
    return [ln[:300] for ln in chosen]


def _tool_version(exe: str, root: Path) -> str | None:
    try:
        p = subprocess.run([exe, "--version"], cwd=root, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (p.stdout or p.stderr).strip().splitlines()
    return redact(out[0], root)[:100] if out else None


def _tool_env(out_dir: Path) -> dict:
    """Keep known tool caches out of the repo tree (verify should leave no residue)."""
    env = dict(os.environ)
    cache = out_dir / "cache"
    env["RUFF_CACHE_DIR"] = str(cache / "ruff")
    env["MYPY_CACHE_DIR"] = str(cache / "mypy")
    env["PYTEST_ADDOPTS"] = (env.get("PYTEST_ADDOPTS", "") + " -p no:cacheprovider").strip()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _blank(check: dict, gate: bool) -> dict:
    return {
        "check_id": check["id"],
        "tool": {"name": check["tool"], "version": None, "source": None},
        "gate": gate,
        "execution_status": "not_run",
        "result_status": "unknown",
        "started_at": None,
        "duration_ms": None,
        "exit_code": None,
        "evidence_ref": None,
        "summary": {"errors": [], "warnings": []},
        "limitations": [],
    }


def run_check(
    check: dict, root: Path, info: dict, out_dir: Path, run_id: str, skip: set[str], only: set[str] | None, timeout: int
) -> dict:
    r = _blank(check, check["gate"])
    applicable, why = check_applicability(check, info)
    if not applicable:
        r["result_status"] = "not_applicable"
        r["limitations"].append(why)
        return r
    if check["id"] in skip or (only is not None and check["id"] not in only):
        r["limitations"].append("not run: excluded by --skip/--only; this is NOT a pass")
        return r

    exe, source = resolve_tool(check["tool"], root)
    if exe is None:
        r["execution_status"] = "unavailable"
        r["summary"]["errors"].append(
            f"tool '{check['tool']}' not found in repo .venv/venv, node_modules/.bin or PATH; "
            f"eqk does not install tools. Install: {check.get('install_hint', 'n/a')}"
        )
        r["limitations"].append("check could not run; result unknown")
        return r
    r["tool"].update(version=_tool_version(exe, root), source=source)

    started = time.monotonic()
    r["started_at"] = _now()
    try:
        p = subprocess.run(
            [exe, *check["args"]],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=_tool_env(out_dir),
        )
        code, output = p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        code, output = None, f"timed out after {timeout}s\n" + str(e.output or "")
    except OSError as e:
        r["execution_status"] = "unavailable"
        r["started_at"] = None
        r["summary"]["errors"].append(redact(f"could not start {check['tool']}: {e}", root))
        return r
    r["duration_ms"] = int((time.monotonic() - started) * 1000)
    r["execution_status"] = "executed"
    r["exit_code"] = code

    output = redact(output, root)
    ev_rel = f"evidence/{run_id}/{check['id']}.log"
    ev = out_dir / ev_rel
    ev.parent.mkdir(parents=True, exist_ok=True)
    ev.write_text(f"$ {check['tool']} {' '.join(check['args'])}\n# exit={code}\n{output}", encoding="utf-8")
    r["evidence_ref"] = ev_rel

    if code is None:
        r["result_status"] = "unknown"
        r["limitations"].append(f"timed out after {timeout}s")
        return r
    mapped = check.get("exit_codes", {"0": "pass"}).get(str(code))
    if mapped is None:
        mapped = "fail" if check["gate"] else "warning"
    r["result_status"] = mapped
    summary = _summarize(output)
    if mapped == "fail":
        r["summary"]["errors"] = summary
    elif mapped in ("warning", "unknown"):
        r["summary"]["warnings"] = summary
        if mapped == "unknown":
            r["limitations"].append(
                f"exit code {code} means the tool ran but produced no verdict (e.g. no tests collected)"
            )
    return r


def overall(checks: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for c in checks:
        counts[c["result_status"]] = counts.get(c["result_status"], 0) + 1
        counts["exec_" + c["execution_status"]] = counts.get("exec_" + c["execution_status"], 0) + 1
    gates = [c for c in checks if c["gate"] and c["result_status"] != "not_applicable"]
    if any(c["result_status"] == "fail" for c in gates):
        status = "fail"
    elif gates and all(c["result_status"] == "pass" for c in gates):
        status = "pass"
    else:  # nothing applicable ran, or some gate has no passing evidence
        status = "incomplete"
    return {"status": status, "counts": counts}


def validate_invariants(report: dict) -> None:
    """Hard guard independent of JSON Schema tooling: no evidence, no pass."""
    for c in report["checks"]:
        if c["result_status"] == "pass" and (c["execution_status"] != "executed" or not c["evidence_ref"]):
            raise AssertionError(f"{c['check_id']}: pass without executed evidence")
        if c["execution_status"] != "executed" and c["result_status"] not in ("not_applicable", "unknown"):
            raise AssertionError(f"{c['check_id']}: non-executed check has verdict {c['result_status']}")
    if report["overall"]["status"] == "pass" and not any(
        c["gate"] and c["result_status"] == "pass" for c in report["checks"]
    ):
        raise AssertionError("overall pass without any passing gate check")


def verify(
    root: Path,
    profile_id: str | None = None,
    skip: set[str] | None = None,
    only: set[str] | None = None,
    out: Path | None = None,
    timeout: int = 900,
) -> tuple[dict, Path]:
    cfg_path = root / CONFIG
    limitations: list[str] = []
    if profile_id is None:
        if not cfg_path.is_file():
            raise RuntimeError("no profile: pass --profile, or run `eqk apply` first")
        profile_id = json.loads(cfg_path.read_text(encoding="utf-8"))["profile"]
    prof = profiles_mod.load(profile_id)

    if out is None:
        if cfg_path.is_file():
            out = root / QUALITY_DIR
        else:  # verify-only on an un-adopted repo: write nothing inside it
            out = Path(tempfile.mkdtemp(prefix="eqk-"))
            limitations.append("eqk not applied in this repo; report written outside the repo")
    out.mkdir(parents=True, exist_ok=True)

    info = detect(root)
    gstate = git_state(root)
    if gstate["dirty"]:
        limitations.append("working tree is dirty: git.commit does not fully identify the verified content")
    if not gstate["is_repo"]:
        limitations.append("not a git repository: no commit identifies the verified content")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    checks = [run_check(c, root, info, out, run_id, skip or set(), only, timeout) for c in prof["checks"]]
    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": _now(),
        "producer": {"name": "eqk", "version": __version__},
        "project": {"id": project_id(root)},
        "git": gstate,
        "profile": {"id": prof["id"], "version": prof["version"]},
        "overall": overall(checks),
        "checks": checks,
        "limitations": limitations
        + [
            "results cover only the checks listed; they are not a statement about overall software correctness",
        ],
    }
    validate_invariants(report)
    rdir = out / "reports"
    rdir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    (rdir / f"{run_id}.json").write_text(text, encoding="utf-8")
    (rdir / "latest.json").write_text(text, encoding="utf-8")
    (rdir / f"{run_id}.md").write_text(render(report), encoding="utf-8")
    return report, rdir / f"{run_id}.json"


ICON = {"pass": "PASS", "fail": "FAIL", "warning": "WARN", "not_applicable": "n/a ", "unknown": "????"}


def render(report: dict) -> str:
    o = report["overall"]
    commit = (report["git"]["commit"] or "no-commit")[:10]
    lines = [
        f"# Quality result: {o['status'].upper()}",
        f"profile {report['profile']['id']} {report['profile']['version']} · commit {commit}"
        f"{' (dirty)' if report['git']['dirty'] else ''} · run {report['run_id']}",
        "",
    ]
    for c in report["checks"]:
        exec_note = "" if c["execution_status"] == "executed" else f" [{c['execution_status']}]"
        lines.append(f"- {ICON[c['result_status']]} {c['check_id']} ({'gate' if c['gate'] else 'info'}){exec_note}")
        for e in c["summary"]["errors"][:5]:
            lines.append(f"    ✗ {e}")
        for w in c["summary"]["warnings"][:3]:
            lines.append(f"    ! {w}")
        for lim in c["limitations"]:
            lines.append(f"    · {lim}")
    if o["status"] == "incomplete":
        lines += ["", "INCOMPLETE: at least one gate check has no passing evidence. This is not a pass."]
    lines += ["", "Limitations:"] + [f"- {x}" for x in report["limitations"]]
    return "\n".join(lines) + "\n"
