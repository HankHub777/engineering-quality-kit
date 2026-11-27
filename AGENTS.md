# Notes for coding agents

- Core logic: `eqk/` (stdlib only — do not add runtime dependencies).
- Profiles are data in `eqk/profiles/*.json`; prefer changing data over code.
- Never weaken the invariant "no evidence, no pass": it is enforced in
  `eqk/verify.py:validate_invariants` and in `schema/quality-result.v0.1.schema.json`.
- `apply` must stay create-only; existing user files are never edited.
- Test: `python -m unittest -v tests.test_unit tests.test_acceptance` (needs ruff,
  pytest, mypy, tsc, npm, markdownlint-cli2 on PATH; missing ones skip).
- Self-check: `python -m eqk verify --profile python-data --out /tmp/eqk-self .`
- After changing behaviour, regenerate evidence: `scripts/poc_evidence.sh`, and
  update `docs/POC_REPORT.md` with what changed.
