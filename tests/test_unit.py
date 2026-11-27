"""Unit tests for pure logic: verdict aggregation, invariants, redaction, profiles."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from eqk import adoption, cli, inspection, profiles
from eqk.util import redact
from eqk import verify as verify_mod
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
        self.assertEqual(overall([c("pass"), c("fail", gate=False)])["status"], "pass")

    def test_gate_not_run_is_incomplete(self) -> None:
        self.assertEqual(overall([c("pass"), c("unknown", execution="not_run")])["status"], "incomplete")


class Summary(unittest.TestCase):
    def test_note_and_file_lines_are_not_errors(self) -> None:
        out = verify_mod._summarize("a.py:1:1: F401 unused\nnote: see docs\nfile: x\nFound 1 error.\n")
        self.assertEqual(out, ["a.py:1:1: F401 unused", "Found 1 error."])


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

    def test_not_run_with_verdict_rejected(self) -> None:
        with self.assertRaises(AssertionError):
            validate_invariants(self.rep(c("fail", execution="not_run"), status="fail"))

    def test_overall_pass_without_passing_gate_rejected(self) -> None:
        with self.assertRaises(AssertionError):
            validate_invariants(self.rep(c("not_applicable", execution="not_run"), status="pass"))

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

    def test_bearer_token_redacted(self) -> None:
        out = redact("Authorization: Bearer abc123\nauthorization basic dXNlcjpw", Path("/r"))
        self.assertNotIn("abc123", out)
        self.assertNotIn("dXNlcjpw", out)

    def test_redaction_stays_on_one_line(self) -> None:
        out = redact("invalid token\nsrc/a.py:1:1 E999", Path("/r"))
        self.assertIn("src/a.py:1:1", out)


class TempRepo(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="eqk-unit-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.root = self.base / "repo"
        self.root.mkdir()


class RevertSafety(TempRepo):
    def test_force_never_deletes_outside_repo(self) -> None:
        outside = self.base / "outside.txt"
        outside.write_text("victim\n")
        absolute = self.base / "absolute.txt"
        absolute.write_text("victim\n")
        digest = hashlib.sha256(b"victim\n").hexdigest()
        (self.root / ".quality").mkdir()
        manifest = {
            "created": [
                {"path": "../outside.txt", "sha256": digest},
                {"path": str(absolute), "sha256": digest},
            ]
        }
        (self.root / adoption.MANIFEST).write_text(json.dumps(manifest))
        res = adoption.revert(self.root, force=True)
        self.assertTrue(outside.exists())
        self.assertTrue(absolute.exists())
        self.assertEqual(res["removed"], [])
        self.assertEqual({k["path"] for k in res["kept"]}, {"../outside.txt", str(absolute)})
        self.assertFalse(res["complete"])


class RevertPreexistingDirs(TempRepo):
    def test_preexisting_quality_subdirs_survive_revert(self) -> None:
        keep = self.root / ".quality/reports/keep.txt"
        keep.parent.mkdir(parents=True)
        keep.write_text("mine\n")
        adoption.apply(self.root, "minimal")
        (self.root / ".quality/evidence").mkdir()  # created after apply: eqk's, removed
        res = adoption.revert(self.root)
        self.assertTrue(res["complete"])
        self.assertTrue(keep.exists())
        self.assertFalse((self.root / ".quality/evidence").exists())


class ApplyPartialFailure(TempRepo):
    def test_manifest_written_when_apply_fails_midway(self) -> None:
        real = adoption.sha256_file
        calls = {"n": 0}

        def flaky(path: Path) -> str:
            calls["n"] += 1
            if calls["n"] > 1:
                raise OSError("disk full")
            return real(path)

        with mock.patch("eqk.adoption.sha256_file", side_effect=flaky):
            with self.assertRaises(OSError):
                adoption.apply(self.root, "minimal")
        manifest = json.loads((self.root / adoption.MANIFEST).read_text())
        self.assertEqual(len(manifest["created"]), 1)
        first = self.root / manifest["created"][0]["path"]
        self.assertTrue(first.exists())
        adoption.revert(self.root)
        self.assertFalse(first.exists())


class CliInternalError(TempRepo):
    def test_internal_error_exits_5(self) -> None:
        (self.root / "README.md").write_text("# x\n")
        with mock.patch("eqk.verify.validate_invariants", side_effect=AssertionError("boom")), mock.patch("sys.stderr"):
            code = cli.main(["verify", "--profile", "minimal", "--out", str(self.base / "out"), str(self.root)])
        self.assertEqual(code, 5)


class StateVsInternalErrors(TempRepo):
    """N-6: bad user state -> exit 4; an eqk bug (e.g. KeyError) -> exit 5."""

    def run_cli(self, *args: str) -> int:
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            code = cli.main([*args, str(self.root)])
        self.stderr = err.getvalue()
        return code

    def write_cfg(self, text: str) -> None:
        (self.root / ".quality").mkdir(exist_ok=True)
        (self.root / adoption.CONFIG).write_text(text)

    def test_profile_bug_keyerror_exits_5(self) -> None:
        broken = {"id": "minimal", "version": "0", "checks": [{"id": "x.noargs", "tool": "python3", "gate": True}]}
        with mock.patch("eqk.profiles.load", return_value=broken):
            code = self.run_cli("verify", "--profile", "minimal", "--out", str(self.base / "out"))
        self.assertEqual(code, 5, self.stderr)

    def test_config_unknown_profile_exits_4(self) -> None:
        self.write_cfg('{"profile": "nope"}')
        self.assertEqual(self.run_cli("verify"), 4, self.stderr)
        self.assertIn("unknown profile", self.stderr)

    def test_config_invalid_json_exits_4(self) -> None:
        self.write_cfg("{not json")
        self.assertEqual(self.run_cli("verify"), 4, self.stderr)
        self.assertIn("eqk.json is invalid", self.stderr)

    def test_config_without_profile_key_exits_4(self) -> None:
        self.write_cfg("{}")
        self.assertEqual(self.run_cli("verify"), 4, self.stderr)
        self.assertIn("eqk.json is invalid", self.stderr)

    def test_invalid_manifest_exits_4(self) -> None:
        for text in ("{not json", "{}"):
            (self.root / ".quality").mkdir(exist_ok=True)
            (self.root / adoption.MANIFEST).write_text(text)
            self.assertEqual(self.run_cli("revert"), 4, self.stderr)
            self.assertIn("applied.json is invalid", self.stderr)


class ArgparseExitCodes(unittest.TestCase):
    """N-1: bad command-line arguments exit 4, never 2 ("incomplete")."""

    def exit_code(self, *argv: str) -> object:
        with mock.patch("sys.stdout", new_callable=io.StringIO), mock.patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as cm:
                cli.main(list(argv))
        return cm.exception.code

    def test_usage_errors_exit_4(self) -> None:
        self.assertEqual(self.exit_code("verify", "--profile", "nope", "."), 4)
        self.assertEqual(self.exit_code("verify", "--no-such-flag", "."), 4)
        self.assertEqual(self.exit_code(), 4)

    def test_help_and_version_exit_0(self) -> None:
        self.assertIn(self.exit_code("--help"), (0, None))
        self.assertIn(self.exit_code("--version"), (0, None))
        self.assertIn(self.exit_code("verify", "--help"), (0, None))


class UnknownCheckIds(TempRepo):
    def test_unknown_skip_or_only_is_usage_error(self) -> None:
        out = self.base / "out"
        for flag in ("--skip", "--only"):
            with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                code = cli.main(["verify", "--profile", "minimal", flag, "py.tests", "--out", str(out), str(self.root)])
            self.assertEqual(code, 4, flag)
            self.assertIn("py.tests", err.getvalue())
            self.assertIn("py.test", err.getvalue().split("available", 1)[1])
        self.assertFalse(out.exists(), "nothing should run or be written")


class Detect(TempRepo):
    def test_non_utf8_ini_does_not_crash(self) -> None:
        (self.root / "setup.cfg").write_bytes(b"[mypy]\n# \xa4\xa4\n")
        (self.root / "tox.ini").write_bytes(b"[pytest]\n# \xa4\xa4\n")
        info = inspection.detect(self.root)
        self.assertEqual(info["configs"]["mypy_config"], [])


class DetectWarnings(TempRepo):
    def test_broken_configs_warn_outside_configs(self) -> None:
        (self.root / "pyproject.toml").write_text("[tool.ruff\n")
        (self.root / "package.json").write_text("{not json")
        info = inspection.detect(self.root)
        self.assertNotIn("warnings", info["configs"])
        joined = " ".join(info["warnings"])
        self.assertIn("pyproject.toml", joined)
        self.assertIn("package.json", joined)
        self.assertIn("Warnings:", inspection.render(inspection.inspect_repo(self.root)))
        plan = adoption.build_plan(self.root, "minimal")
        self.assertTrue(any("package.json" in w for w in plan["warnings"]))

    def test_no_warnings_key_is_empty_list(self) -> None:
        self.assertEqual(inspection.detect(self.root)["warnings"], [])


class FileScanCap(TempRepo):
    def test_truncated_scan_warns_and_reaches_report(self) -> None:
        for i in range(5):
            (self.root / f"n{i}.txt").write_text("x\n")
        with mock.patch("eqk.util.MAX_FILES", 3):
            info = inspection.detect(self.root)
            self.assertTrue(any("file scan stopped at 3 files" in w for w in info["warnings"]), info["warnings"])
            report, _ = verify_mod.verify(self.root, "minimal", out=self.base / "out")
        self.assertTrue(any("file scan stopped" in x for x in report["limitations"]), report["limitations"])


def symlink_or_skip(tc: unittest.TestCase, target: Path, link: Path) -> None:
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as e:
        tc.skipTest(f"symlinks unavailable: {e}")


def tree(path: Path) -> dict[str, bytes]:
    return {p.relative_to(path).as_posix(): p.read_bytes() if p.is_file() else b"<dir>" for p in path.rglob("*")}


class QualityDirSymlinks(TempRepo):
    """N-2: eqk never writes or deletes through a symlink in .quality."""

    def victim(self) -> Path:
        v = self.base / "victim"
        (v / "evidence").mkdir(parents=True)
        (v / "evidence/data.txt").write_text("precious\n")
        (v / "applied.json").write_text('{"created": []}')
        return v

    def run_cli(self, *args: str) -> int:
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            code = cli.main([*args, str(self.root)])
        self.stderr = err.getvalue()
        return code

    def test_revert_refuses_symlinked_quality_dir(self) -> None:
        v = self.victim()
        symlink_or_skip(self, Path("../victim"), self.root / ".quality")
        before = tree(v)
        self.assertEqual(self.run_cli("revert"), 4, self.stderr)
        self.assertEqual(tree(v), before)

    def test_apply_refuses_symlinked_quality_dir(self) -> None:
        v = self.base / "victim"
        v.mkdir()
        symlink_or_skip(self, Path("../victim"), self.root / ".quality")
        self.assertEqual(self.run_cli("apply", "--profile", "minimal", "--yes"), 4, self.stderr)
        self.assertEqual(list(v.iterdir()), [])

    def test_verify_refuses_symlinked_report(self) -> None:
        adoption.apply(self.root, "minimal")
        target = self.base / "somefile"
        target.write_text("mine\n")
        (self.root / ".quality/reports").mkdir()
        symlink_or_skip(self, target, self.root / ".quality/reports/latest.json")
        self.assertEqual(self.run_cli("verify"), 4, self.stderr)
        self.assertEqual(target.read_text(), "mine\n")

    def test_normal_adopted_repo_is_safe(self) -> None:
        self.assertTrue(adoption.quality_dir_safe(self.root)[0])  # no .quality yet
        adoption.apply(self.root, "minimal")
        ok, why = adoption.quality_dir_safe(self.root)
        self.assertTrue(ok, why)


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
