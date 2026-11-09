"""P0 acceptance tests. Each test maps to one PoC criterion (AC-n, see docs/POC_REPORT.md).

They run the real CLI as a subprocess against copies of examples/ in temp git repos,
with real tools (ruff, pytest, mypy, tsc, npm, markdownlint-cli2). A test whose tool is
missing is SKIPPED with the reason — never silently passed.

Run:  PATH=<tools>:$PATH python -m unittest -v tests.test_acceptance
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
EXAMPLES = KIT / "examples"
SCHEMA = json.loads((KIT / "schema/quality-result.v0.1.schema.json").read_text())

try:
    import jsonschema
except ImportError:  # validated by invariants only
    jsonschema = None


def need(*tools: str) -> None:
    missing = [t for t in tools if shutil.which(t) is None]
    if missing:
        raise unittest.SkipTest(f"tool(s) not on PATH: {', '.join(missing)}")


def eqk(root: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    e = dict(os.environ if env is None else env)
    e["PYTHONPATH"] = str(KIT)
    e["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run([sys.executable, "-m", "eqk", *args, str(root)], capture_output=True, text=True, env=e)


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


def snapshot(root: Path) -> dict[str, str]:
    out = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and not rel.startswith(".git/") and "__pycache__" not in rel and "_cache" not in rel:
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def latest_report(root: Path) -> dict:
    return json.loads((root / ".quality/reports/latest.json").read_text())


def check(report: dict, cid: str) -> dict:
    return next(c for c in report["checks"] if c["check_id"] == cid)


class Repo:
    """Copy an example into a fresh temp git repo with one commit."""

    def __init__(self, example: str):
        self.tmp = tempfile.TemporaryDirectory(prefix="eqk-ac-")
        self.root = Path(self.tmp.name) / example
        shutil.copytree(
            EXAMPLES / example, self.root, ignore=shutil.ignore_patterns("__pycache__", ".*_cache", "node_modules")
        )
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", "-A")
        git(self.root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "init")

    def cleanup(self) -> None:
        self.tmp.cleanup()


class AcceptanceBase(unittest.TestCase):
    example = ""

    def setUp(self) -> None:
        self.repo = Repo(self.example)
        self.root = self.repo.root
        self.addCleanup(self.repo.cleanup)

    def assertValidReport(self, report: dict) -> None:
        if jsonschema is not None:
            jsonschema.validate(report, SCHEMA)
        for c in report["checks"]:
            if c["result_status"] == "pass":
                self.assertEqual(c["execution_status"], "executed")
                self.assertTrue((self.root / ".quality" / c["evidence_ref"]).is_file())
        text = json.dumps(report)
        self.assertNotIn(str(self.root), text, "report leaks an absolute path")
        self.assertNotIn(str(Path.home()), text, "report leaks the home directory")


class AC1NewPythonProject(AcceptanceBase):
    """AC-1: a brand-new Python project adopts eqk and passes with real evidence."""

    example = "python-new"

    def test_inspect_is_read_only(self) -> None:
        before = snapshot(self.root)
        r = eqk(self.root, "inspect", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        info = json.loads(r.stdout)
        self.assertIn("python", info["languages"])
        self.assertEqual(info["configs"]["ruff_config"], [])
        self.assertEqual(info["suggested_profile"]["id"], "python-data")
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(git(self.root, "status", "--porcelain"), "")

    def test_plan_then_apply_then_verify_pass(self) -> None:
        need("ruff", "pytest", "mypy")
        before = snapshot(self.root)
        plan = json.loads(eqk(self.root, "plan", "--profile", "python-data", "--json").stdout)
        self.assertEqual(snapshot(self.root), before, "plan must not write")
        created = {a["path"] for a in plan["actions"] if a["op"] == "create"}
        self.assertEqual(created, {".quality/eqk.json", ".quality/.gitignore", "ruff.toml"})

        r = eqk(self.root, "apply", "--profile", "python-data")
        self.assertEqual(r.returncode, 3, "apply without --yes must not write")
        self.assertEqual(snapshot(self.root), before)

        self.assertEqual(eqk(self.root, "apply", "--profile", "python-data", "--yes").returncode, 0)
        r = eqk(self.root, "verify")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rep = latest_report(self.root)
        self.assertValidReport(rep)
        self.assertEqual(rep["overall"]["status"], "pass")
        for cid in ("py.lint", "py.test"):
            self.assertEqual(check(rep, cid)["result_status"], "pass")
        self.assertEqual(check(rep, "ts.typecheck")["result_status"], "not_applicable")
        self.assertRegex(rep["git"]["commit"] or "", "^[0-9a-f]{40}$")


class AC2ExistingPythonProject(AcceptanceBase):
    """AC-2/AC-4/AC-5/AC-10: existing config preserved; injected defects are caught; same flow reused."""

    example = "python-existing"

    def test_existing_config_untouched(self) -> None:
        need("ruff", "pytest")
        before = snapshot(self.root)
        plan = json.loads(eqk(self.root, "plan", "--profile", "python-data", "--json").stdout)
        kept = {a["path"] for a in plan["actions"] if a["op"] == "keep"}
        self.assertIn("ruff.toml", kept, "must not add ruff.toml when pyproject has [tool.ruff]")
        self.assertIn(".github/workflows/ci.yml", kept)
        self.assertIn(".pre-commit-config.yaml", kept)

        self.assertEqual(eqk(self.root, "apply", "--profile", "python-data", "--yes").returncode, 0)
        after = snapshot(self.root)
        for path, digest in before.items():
            self.assertEqual(after.get(path), digest, f"{path} was modified or deleted")
        self.assertEqual(
            set(after) - set(before), {".quality/eqk.json", ".quality/.gitignore", ".quality/applied.json"}
        )
        self.assertEqual(eqk(self.root, "verify").returncode, 0)
        self.assertValidReport(latest_report(self.root))

    def test_injected_lint_defect_fails_gate(self) -> None:
        need("ruff", "pytest")
        eqk(self.root, "apply", "--profile", "minimal", "--yes")
        mod = self.root / "inventory/stock.py"
        mod.write_text("import os\n" + mod.read_text())
        r = eqk(self.root, "verify")
        self.assertEqual(r.returncode, 1, r.stdout)
        rep = latest_report(self.root)
        self.assertValidReport(rep)
        self.assertEqual(rep["overall"]["status"], "fail")
        lint = check(rep, "py.lint")
        self.assertEqual(lint["result_status"], "fail")
        self.assertTrue(any("F401" in e for e in lint["summary"]["errors"]), lint["summary"])
        self.assertTrue(rep["git"]["dirty"])

    def test_injected_logic_defect_fails_tests(self) -> None:
        need("ruff", "pytest")
        eqk(self.root, "apply", "--profile", "minimal", "--yes")
        mod = self.root / "inventory/stock.py"
        mod.write_text(mod.read_text().replace("max(item.on_hand - item.reserved, 0)", "item.on_hand - item.reserved"))
        self.assertEqual(eqk(self.root, "verify").returncode, 1)
        rep = latest_report(self.root)
        self.assertEqual(check(rep, "py.test")["result_status"], "fail")
        self.assertEqual(check(rep, "py.lint")["result_status"], "pass")


class AC3TypeScriptProject(AcceptanceBase):
    """AC-3/AC-5: TypeScript project adopts eqk; an injected type error is caught."""

    example = "typescript-web"

    def test_adopt_verify_and_catch_type_error(self) -> None:
        need("tsc", "npm", "node")
        info = json.loads(eqk(self.root, "inspect", "--json").stdout)
        self.assertEqual(info["suggested_profile"]["id"], "typescript-web")
        before = snapshot(self.root)
        self.assertEqual(eqk(self.root, "apply", "--profile", "typescript-web", "--yes").returncode, 0)
        for path, digest in before.items():
            self.assertEqual(snapshot(self.root).get(path), digest)

        r = eqk(self.root, "verify")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rep = latest_report(self.root)
        self.assertValidReport(rep)
        self.assertEqual(check(rep, "ts.typecheck")["result_status"], "pass")
        self.assertEqual(check(rep, "js.test")["result_status"], "pass")
        self.assertEqual(check(rep, "ts.lint")["result_status"], "not_applicable")

        src = self.root / "src/price.ts"
        src.write_text(src.read_text() + '\nexport const broken: number = "not a number";\n')
        self.assertEqual(eqk(self.root, "verify").returncode, 1)
        tc = check(latest_report(self.root), "ts.typecheck")
        self.assertEqual(tc["result_status"], "fail")
        self.assertTrue(any("TS2322" in e for e in tc["summary"]["errors"]), tc["summary"])


class AC6NotRunIsNotPass(AcceptanceBase):
    """AC-6: skipped tests are reported not_run/unknown and the run is incomplete, never pass."""

    example = "python-new"

    def test_skip_tests(self) -> None:
        need("ruff")
        eqk(self.root, "apply", "--profile", "minimal", "--yes")
        r = eqk(self.root, "verify", "--skip", "py.test")
        self.assertEqual(r.returncode, 2, r.stdout)
        rep = latest_report(self.root)
        self.assertValidReport(rep)
        t = check(rep, "py.test")
        self.assertEqual((t["execution_status"], t["result_status"]), ("not_run", "unknown"))
        self.assertIsNone(t["evidence_ref"])
        self.assertEqual(rep["overall"]["status"], "incomplete")
        self.assertIn("INCOMPLETE", r.stdout)

    def test_no_tests_collected_is_unknown(self) -> None:
        need("ruff", "pytest")
        eqk(self.root, "apply", "--profile", "minimal", "--yes")
        (self.root / "tests/test_calc.py").write_text("# all tests removed\n")
        self.assertEqual(eqk(self.root, "verify").returncode, 2)
        t = check(latest_report(self.root), "py.test")
        self.assertEqual((t["execution_status"], t["exit_code"], t["result_status"]), ("executed", 5, "unknown"))


class AC7ToolUnavailable(AcceptanceBase):
    """AC-7: when tools are missing (offline / locked-down), eqk says so and does not pass."""

    example = "python-new"

    def test_missing_tools(self) -> None:
        eqk(self.root, "apply", "--profile", "python-data", "--yes")
        env = dict(os.environ)
        env["PATH"] = "/usr/bin:/bin"  # system dirs only: no ruff/pytest/mypy
        if any(shutil.which(t, path=env["PATH"]) for t in ("ruff", "pytest")):
            self.skipTest("ruff/pytest found in system dirs; cannot simulate absence")
        r = eqk(self.root, "verify", env=env)
        self.assertEqual(r.returncode, 2, r.stdout)
        rep = latest_report(self.root)
        self.assertValidReport(rep)
        lint = check(rep, "py.lint")
        self.assertEqual((lint["execution_status"], lint["result_status"]), ("unavailable", "unknown"))
        self.assertIn("pip install ruff", lint["summary"]["errors"][0])
        self.assertEqual(rep["overall"]["status"], "incomplete")


class AC8Revert(AcceptanceBase):
    """AC-8: revert removes exactly what apply added; human edits are protected."""

    example = "python-new"

    def test_revert_restores_tree(self) -> None:
        before = snapshot(self.root)
        eqk(self.root, "apply", "--profile", "python-data", "--yes")
        eqk(self.root, "verify")  # creates evidence/reports too
        r = eqk(self.root, "revert")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(git(self.root, "status", "--porcelain", "--ignored"), "")

    def test_revert_keeps_human_edits(self) -> None:
        eqk(self.root, "apply", "--profile", "python-data", "--yes")
        cfg = self.root / "ruff.toml"
        cfg.write_text(cfg.read_text() + "line-length = 88\n")
        r = eqk(self.root, "revert")
        self.assertEqual(r.returncode, 4)
        self.assertTrue(cfg.exists(), "edited file must be kept")
        self.assertIn("edited since apply", r.stdout)

    def test_apply_refuses_twice(self) -> None:
        eqk(self.root, "apply", "--profile", "minimal", "--yes")
        r = eqk(self.root, "apply", "--profile", "python-data", "--yes")
        self.assertEqual(r.returncode, 4)
        self.assertIn("already applied", r.stderr)


class DocsProfile(AcceptanceBase):
    """Docs profile smoke test (not a P0 criterion)."""

    example = "docs-basic"

    def test_docs(self) -> None:
        need("markdownlint-cli2")
        eqk(self.root, "apply", "--profile", "docs", "--yes")
        self.assertEqual(eqk(self.root, "verify").returncode, 0)
        rep = latest_report(self.root)
        self.assertEqual(check(rep, "docs.markdownlint")["result_status"], "pass")
        self.assertEqual(check(rep, "docs.vale")["result_status"], "not_applicable")
        (self.root / "README.md").write_text("no heading\n# Title\n")
        self.assertEqual(eqk(self.root, "verify").returncode, 1)


class VerifyWithoutAdoption(AcceptanceBase):
    """Verify-only mode on an un-adopted repo writes nothing inside it."""

    example = "python-new"

    def test_verify_only(self) -> None:
        need("ruff", "pytest")
        before = snapshot(self.root)
        out = Path(self.repo.tmp.name) / "out"
        r = eqk(self.root, "verify", "--profile", "minimal", "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(snapshot(self.root), before)
        self.assertTrue((out / "reports/latest.json").is_file())


if __name__ == "__main__":
    unittest.main()
