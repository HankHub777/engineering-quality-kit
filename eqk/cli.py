"""Command line: inspect -> plan -> apply -> verify (-> revert).

Exit codes: 0 ok/pass · 1 quality gate failed · 2 incomplete (some gate has no evidence)
            3 not applied (missing --yes) · 4 usage / state error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, adoption, inspection, verify
from . import profiles as profiles_mod


def _csv(s: str | None) -> set[str] | None:
    return {x.strip() for x in s.split(",") if x.strip()} if s else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eqk", description="Engineering Quality Kit")
    ap.add_argument("--version", action="version", version=f"eqk {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("inspect", help="read-only: detect languages, existing config, tools")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("plan", help="show what apply would create/keep, and which checks will run")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--profile", required=True, choices=profiles_mod.list_ids())
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("apply", help="create (never overwrite) the planned files")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--profile", required=True, choices=profiles_mod.list_ids())
    p.add_argument("--yes", action="store_true", help="confirm; without it apply only prints the plan")

    p = sub.add_parser("verify", help="run checks and write a JSON report + evidence")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--profile", choices=profiles_mod.list_ids(), help="default: the applied profile")
    p.add_argument("--skip", help="comma-separated check ids to not run (reported as not_run)")
    p.add_argument("--only", help="comma-separated check ids to run; others are not_run")
    p.add_argument("--out", help="output dir (default: .quality/ if applied, else a temp dir)")
    p.add_argument("--timeout", type=int, default=900, help="seconds per check")
    p.add_argument("--json", action="store_true", help="print the JSON report instead of the summary")

    p = sub.add_parser("revert", help="remove exactly the files apply created")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--force", action="store_true", help="also remove files edited since apply")

    sub.add_parser("profiles", help="list profiles")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "profiles":
            for pid in profiles_mod.list_ids():
                prof = profiles_mod.load(pid)
                print(f"{pid:15} {prof['version']}  {prof['description']}")
            return 0
        root = Path(a.path).resolve()
        if not root.is_dir():
            print(f"eqk: not a directory: {a.path}", file=sys.stderr)
            return 4
        if a.cmd == "inspect":
            info = inspection.inspect_repo(root)
            print(json.dumps(info, indent=2) if a.json else inspection.render(info))
            return 0
        if a.cmd == "plan":
            plan = adoption.build_plan(root, a.profile)
            print(json.dumps(plan, indent=2) if a.json else adoption.render_plan(plan))
            return 0
        if a.cmd == "apply":
            if not a.yes:
                print(adoption.render_plan(adoption.build_plan(root, a.profile)))
                print("\nNot applied: re-run with --yes to create the files above.")
                return 3
            res = adoption.apply(root, a.profile)
            for c in res["manifest"]["created"]:
                print(f"created {c['path']}")
            for act in res["plan"]["actions"]:
                if act["op"] == "keep":
                    print(f"kept    {act['path']} ({act['reason']})")
            print("Manifest: .quality/applied.json · undo with `eqk revert`")
            return 0
        if a.cmd == "verify":
            report, path = verify.verify(
                root, a.profile, _csv(a.skip), _csv(a.only), Path(a.out).resolve() if a.out else None, a.timeout
            )
            print(json.dumps(report, indent=2, ensure_ascii=False) if a.json else verify.render(report))
            print(f"Report: {path}", file=sys.stderr)
            return {"pass": 0, "fail": 1, "incomplete": 2}[report["overall"]["status"]]
        if a.cmd == "revert":
            res = adoption.revert(root, a.force)
            for r in res["removed"]:
                print(f"removed {r}")
            for k in res["kept"]:
                print(f"kept    {k['path']} ({k['reason']})")
            return 0 if res["complete"] else 4
    except (RuntimeError, KeyError) as e:
        print(f"eqk: {e}", file=sys.stderr)
        return 4
    return 4
