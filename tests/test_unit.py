"""Unit tests for pure logic: verdict aggregation, invariants, redaction, profiles."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from eqk import profiles
from eqk.util import redact
from eqk.verify import overall, validate_invariants

KIT = Path(__file__).resolve().parents[1]


def c(result: str, gate: bool = True, execution: str = "executed", evidence: str | None = "e.log") -> dict:
    return {
        "check_id": "x",
        "gate": gate,
        "execution_status": execution,
        "result_status": result,
        "evidence_ref": evidence if execution == "executed" else None,
    }


class Overall(unittest.TestCase):
    def test_all_gates_pass(self) -> None:
        self.assertEqual(overall([c("pass"), c("warning", gate=False)])["status"], "pass")

    def test_any_gate_fail(self) -> None:
        self.assertEqual(overall([c("pass"), c("fail")])["status"], "fail")

    def test_unavailable_gate_is_incomplete(self) -> None:
        self.assertEqual(overall([c("pass"), c("unknown", execution="unavailable")])["status"], "incomplete")

    def test_nothing_applicable_is_incomplete(self) -> None:
        self.assertEqual(overall([c("not_applicable", execution="not_run")])["status"], "incomplete")

    def test_non_gate_fail_does_not_block(self) -> None:
        self.assertEqual(overall([c("pass"), c("warning", gate=False)])["status"], "pass")


class Invariants(unittest.TestCase):
    def rep(self, *checks: dict, status: str = "pass") -> dict:
        return {"checks": list(checks), "overall": {"status": status}}

    def test_pass_without_evidence_rejected(self) -> None:
        with self.assertRaises(AssertionError):
            validate_invariants(self.rep(c("pass", evidence=None)))

    def test_not_run_pass_rejected(self) -> None:
        bad = c("pass")
        bad["execution_status"] = "not_run"
        with self.assertRaises(AssertionError):
            validate_invariants(self.rep(bad))

    def test_ok(self) -> None:
        validate_invariants(self.rep(c("pass")))


class Redaction(unittest.TestCase):
    def test_paths_and_secrets(self) -> None:
        root = Path("/work/acme-secret-project")
        text = f"{root}/a.py:1: error\nAPI_KEY=abc123 token: zzz\n{Path.home()}/x ghp_{'a' * 30}"
        out = redact(text, root)
        self.assertNotIn(str(root), out)
        self.assertNotIn("abc123", out)
        self.assertNotIn("zzz", out)
        self.assertNotIn("ghp_", out)
        self.assertIn("<repo>/a.py", out)


class Profiles(unittest.TestCase):
    def test_all_load_and_ids_unique(self) -> None:
        self.assertEqual(profiles.list_ids(), ["docs", "minimal", "python-data", "typescript-web"])
        for pid in profiles.list_ids():
            p = profiles.load(pid)
            ids = [ch["id"] for ch in p["checks"]]
            self.assertEqual(len(ids), len(set(ids)), pid)
            for sc in p.get("scaffold", []):
                self.assertTrue(profiles.template(sc["template"]))

    def test_extends(self) -> None:
        ids = {ch["id"] for ch in profiles.load("python-data")["checks"]}
        self.assertTrue({"py.lint", "py.test", "py.format", "py.types"} <= ids)


class Skill(unittest.TestCase):
    def test_frontmatter(self) -> None:
        text = (KIT / "skills/quality-adoption/SKILL.md").read_text()
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        assert m is not None
        fm = m.group(1)
        self.assertRegex(fm, r"(?m)^name: quality-adoption$")
        self.assertRegex(fm, r"(?m)^description: .{40,1024}$")
        self.assertRegex(fm, r"(?m)^\s+version: \d+\.\d+\.\d+$")
        cases = json.loads((KIT / "skills/quality-adoption/evals/cases.json").read_text())
        self.assertGreaterEqual(len(cases["cases"]), 3)


if __name__ == "__main__":
    unittest.main()
