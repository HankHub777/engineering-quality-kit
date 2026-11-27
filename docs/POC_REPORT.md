# P0 PoC report

Run: 2026-11-27 (after review round 2; first run 2026-11-09), macOS arm64, Python 3.12.10, ruff 0.17.4, pytest 9.2.0, mypy 2.4.1,
tsc 5.9.3, Node 24.16.0, markdownlint-cli2 0.24.0. Full environment:
[poc-evidence/environment.txt](poc-evidence/environment.txt).

Reproduce: put the tools on `PATH`, then `scripts/poc_evidence.sh`.

**Result: 60 tests, 60 passed, 0 skipped** ([test-run.txt](poc-evidence/test-run.txt)).

## Acceptance criteria

| # | Criterion (from the brief) | Evidence | Status |
|---|---|---|---|
| AC-1 | A brand-new Python project adopts successfully | `AC1NewPythonProject.*` — inspect is read-only, plan writes nothing, apply without `--yes` writes nothing, verify → `pass` with lint + tests executed | ✅ verified |
| AC-2 | An existing Python project with code and config adopts successfully | `AC2ExistingPythonProject.test_existing_config_untouched`; [01-pass.json](poc-evidence/01-pass.json) | ✅ verified |
| AC-3 | A TypeScript project adopts successfully | `AC3TypeScriptProject` — tsc + `npm test` pass | ✅ verified |
| AC-4 | Existing config not improperly overwritten | Byte-hash comparison of every pre-existing file before/after apply (pyproject `[tool.ruff]`, mypy.ini, CI workflow, pre-commit); `ruff.toml` *not* created | ✅ verified |
| AC-5 | An injected defect is caught by the gate | Unused import → `py.lint` fail (F401); logic change → `py.test` fail; TS type error → `ts.typecheck` fail (TS2322); [04-fail-injected-defect.txt](poc-evidence/04-fail-injected-defect.txt) | ✅ verified |
| AC-6 | Un-run tests are not reported as passed | `--skip py.test` → `not_run/unknown`, overall `incomplete`, exit 2; zero tests collected → `executed/unknown`; [02-incomplete-skipped.txt](poc-evidence/02-incomplete-skipped.txt) | ✅ verified |
| AC-7 | Tool unavailability is reported clearly | PATH without tools → `unavailable/unknown` + install hint, overall `incomplete`; [03-incomplete-unavailable.txt](poc-evidence/03-incomplete-unavailable.txt) | ✅ verified |
| AC-8 | Adoption can be disabled / reverted | `revert` restores a byte-identical tree with empty `git status --ignored`; human-edited files are kept; [05-revert.txt](poc-evidence/05-revert.txt) | ✅ verified |
| AC-9 | Structured JSON report | Every acceptance run validated against `schema/quality-result.v0.1.schema.json` (jsonschema) + invariant checker; no absolute paths or home dir in reports | ✅ verified |
| AC-10 | A second project reuses the flow without redesign | Same CLI and profiles used unchanged across 4 example repos (2 Python, 1 TS, 1 docs) | ✅ verified |
| — | Kit tests itself | eqk verifies its own repo with `python-data`: pass, including format and mypy ([06-self-check.txt](poc-evidence/06-self-check.txt)) | ✅ verified |

## Defects found by the PoC and fixed

1. **Tool caches leaked into the target repo** (`.ruff_cache`, `.pytest_cache`,
   `.mypy_cache`) so revert left residue. Fix: verify redirects caches to `.quality/cache/`.
2. **ruff defaults drifted** — ruff 0.17 without config flagged `I001` and `RUF100` on
   code that was clean under the older default set. Confirms D-pinning in ADR-0001;
   the `minimal` profile, which adds no config, inherits whatever the installed ruff
   defaults are (documented in LIMITATIONS).
3. **Error summaries showed only "Found N errors"**. Fix: summaries prefer
   `file:line` findings and ruff runs with `--output-format=concise`.
4. **The kit's own pytest run collected example tests**; fixed with `testpaths`.
5. **Docs profile on the kit's own docs failed** on cosmetic rules (MD013 line length,
   MD060 table pipe spacing) and one real issue (code fence without a language). The
   cosmetic rules are now off in the `docs` template; the real one was fixed. The kit's
   docs pass `--profile docs`.
6. **The kit's self-check passed only because the evidence script exported `PYTHONPATH`.**
   A clean checkout's `pytest` could not import `eqk`. Fix: `pythonpath = ["."]` in
   `pyproject.toml`; the script now unsets `PYTHONPATH` for the self-check.

## Defects found by review and fixed

Review round 1 (branch `fix/review-round-1`, one commit per item). Each fix has a test
that failed before the fix.

| ID | Defect | Fix | Test |
|---|---|---|---|
| A-3 | `revert --force` could delete files outside the repo via a crafted `applied.json` (`../x`, absolute path) | Paths outside the repo are refused and listed as kept, even with `--force` | `RevertSafety` |
| V-5 | `Authorization: Bearer <token>` leaked the token; redaction crossed newlines | Scheme-aware value, single-line separator | `Redaction.test_bearer_*`, `test_redaction_stays_on_one_line` |
| A-1 | A failure midway through `apply` left created files with no manifest | Manifest written in `finally` | `ApplyPartialFailure` |
| V-1 | An internal crash exited 1 ("gate failed") | **New exit code 5 = internal error** | `CliInternalError` |
| I-1 | Non-UTF-8 `setup.cfg` / `tox.ini` crashed inspect/plan/apply/verify | `UnicodeDecodeError` caught | `Detect` |
| T-1 | Duplicate `overall` test; invariant rules 2 and 3 untested | Tests fixed / added | `Overall`, `Invariants` |
| V-2 | Tool errors (ruff 2, pytest 3/4, mypy 2) reported as quality `fail` | **Profile exit-code maps now give `unknown`** (data only) | `ToolErrorIsNotAVerdict` |
| V-4 | Unknown ids in `--skip` / `--only` silently accepted | Usage error (exit 4) listing available ids | `UnknownCheckIds` |
| V-3 | Timeout evidence stored as `b'...'`; npm's child `node` kept running after timeout (reproduced) | Output decoded; checks run in their own process group on POSIX, group killed on timeout | `Timeout` (first timeout test) |
| I-2 | Detection warnings stored inside `configs`; broken `package.json` silent | Top-level `warnings`, shown by inspect and plan | `DetectWarnings` |
| I-3 | File-walk cap (50,000) truncated silently | Warning; detection warnings copied into report `limitations` | `FileScanCap` |
| A-2 | `revert` deleted pre-existing `.quality/{evidence,reports,cache}` | Manifest records `preexisting_dirs`; revert skips them | `RevertPreexistingDirs` |
| V-6 | Error hint `"e:"` matched `note:`, `file:` … | Removed; F401 / TS2322 still in summaries | `Summary`, AC-2/AC-3 |
| I-4, I-5 | `modified_files: []` reads like a measurement; detection scope gaps undocumented | README and LIMITATIONS updated | — |

Side effect of A-2 on this script: undoing an adoption with `git reset` leaves eqk's
ignored run outputs behind, which the next `apply` now treats as pre-existing. The
evidence script therefore runs `git clean -fdx` before re-applying.

### Reviewer decisions on round 1

- **V-1** (exit 5 = internal error): confirmed; completed by N-6.
- **V-2** (exit-code maps): confirmed, including pytest exit 2 staying `fail` (collection
  errors are real defects). Signal kills are handled by N-9.
- **A-2 side effect**: accepted. Run-output dirs left by an adoption undone with
  `git reset` are treated as pre-existing and survive `revert` (fails toward keeping
  data). Documented (N-10); no marker files.
- **N-2**: `verify` refuses (exit 4) when `.quality` is unsafe; no temp-dir fallback, so CI
  reading `.quality/reports/latest.json` cannot silently read a stale report.

## Defects found by review round 2 and fixed

Branch `fix/review-round-2`, one commit per item. "Reproduced" means a test showed the
defect before the code was changed.

| ID | Defect | Reproduced? | Fix | Test |
|---|---|---|---|---|
| N-2 | A symlink in `.quality` let revert delete, apply create, and verify overwrite files outside the repo | yes (all three) | `quality_dir_safe()`; apply, revert and verify (default output) refuse with exit 4 | `QualityDirSymlinks` |
| N-7 | Ctrl+C stopped eqk but left the tool's process group running (side effect of V-3) | yes | kill the tool's group on any interrupt, bounded cleanup, re-raise; no report | `Interrupt` |
| N-6 | An eqk bug raising `KeyError` exited 4; invalid `eqk.json` / `applied.json` exited 5 or 4 by accident | yes | only `RuntimeError` = usage/state error; invalid config/manifest → `RuntimeError` | `StateVsInternalErrors` |
| N-1 | Invalid command-line arguments exited 2 ("incomplete") | yes | parser `error()` exits 4 | `ArgparseExitCodes` |
| N-3 | A file whose write failed after `open('x')` was not in the manifest | yes | hash from content; record right after `open('x')` | `ApplyPartialFailure` |
| N-4 | Profiles changed by V-2 still said `0.1.0` | n/a | `minimal`, `python-data`, `typescript-web` → `0.1.1`; pinned (version, hash) test; AGENTS.md rule | `Profiles.test_verdict_changes_bump_version` |
| N-8 | After a timeout, a `setsid` descendant holding the pipe made output collection wait forever | yes (2s timeout ran past a 20s hard limit) | second `communicate()` bounded to 5s; limitation added | `RunCheckProcesses` |
| N-9 | A tool killed by a signal (exit −9) was reported as `fail` | yes | negative exit code → `unknown` + limitation | `RunCheckProcesses` |
| N-5, N-10 | Windows timeout gap; A-2 side effect undocumented | n/a | LIMITATIONS updated (+ P1 row) | — |

## Not verified (honest gaps)

- Windows and Linux (only macOS arm64 was run). Repo-venv lookup includes `Scripts/`
  but is untested.
- Python 3.9/3.10 (code avoids 3.10+ syntax at runtime, but only 3.12 was run).
- Real-world repos: only the 4 bundled examples. No monorepo, no repo with both
  Python and TS, no repo with broken/partial config.
- `ts.lint` (ESLint) and `docs.vale` executed paths — only their `not_applicable` paths ran.
- Timeout and interrupt handling are tested on POSIX only (`npm test`, a forking Python
  script, SIGINT, SIGKILL); Windows only kills the direct child (no process-group kill).
- Symlink refusal (N-2) is tested on macOS; Windows without symlink privilege skips it.
- The Agent Skill's behavioural cases ([evals/cases.json](../skills/quality-adoption/evals/cases.json))
  have **not** been run against an agent; only the skill's format is tested.
- Redaction is pattern-based; it is a safety net, not a guarantee.
