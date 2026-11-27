# P0 PoC report

Run: 2026-11-09, macOS arm64, Python 3.12.10, ruff 0.17.4, pytest 9.2.0, mypy 2.4.1,
tsc 5.9.3, Node 24.16.0, markdownlint-cli2 0.24.0. Full environment:
[poc-evidence/environment.txt](poc-evidence/environment.txt).

Reproduce: put the tools on `PATH`, then `scripts/poc_evidence.sh`.

**Result: 26 tests, 26 passed, 0 skipped** ([test-run.txt](poc-evidence/test-run.txt)).

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

## Not verified (honest gaps)

- Windows and Linux (only macOS arm64 was run). Repo-venv lookup includes `Scripts/`
  but is untested.
- Python 3.9/3.10 (code avoids 3.10+ syntax at runtime, but only 3.12 was run).
- Real-world repos: only the 4 bundled examples. No monorepo, no repo with both
  Python and TS, no repo with broken/partial config.
- `ts.lint` (ESLint) and `docs.vale` executed paths — only their `not_applicable` paths ran.
- Timeout handling (`--timeout`) has no test.
- The Agent Skill's behavioural cases ([evals/cases.json](../skills/quality-adoption/evals/cases.json))
  have **not** been run against an agent; only the skill's format is tested.
- Redaction is pattern-based; it is a safety net, not a guarantee.
