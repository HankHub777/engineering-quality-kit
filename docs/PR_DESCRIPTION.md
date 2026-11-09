# P0: Engineering Quality Kit proof of concept

## What

A zero-dependency Python CLI (`eqk`), with the commands `inspect` → `plan` → `apply` → `verify` → `revert`. It adopts quality gates in new and existing repos by reusing ruff, pytest, mypy, tsc, npm test and markdownlint. It also includes:

- 4 profiles
- the result schema v0.1
- the `quality-adoption` Agent Skill
- 4 example repos
- the ADRs
- the PoC evidence

## Evidence

- 26/26 unit and acceptance tests pass with real tools, 0 skipped (`docs/poc-evidence/test-run.txt`).
- All 10 acceptance criteria are mapped to tests in `docs/POC_REPORT.md`.
- The kit passes its own `python-data` and `docs` profiles.

## Review focus

- `eqk/verify.py`: `overall()` and `validate_invariants()` enforce "no evidence, no pass".
- `eqk/adoption.py`: `apply` only creates files, and `revert` is hash-guarded.
- `docs/adr/0001-p0-architecture.md` D7: items cut, merged or deferred from the brief.

## Not verified

- Only macOS was run, not Windows or Linux.
- Only Python 3.12 was run, not Python 3.9 or 3.10.
- No real-world repos, only the bundled examples.
- The ESLint and Vale checks never actually ran.
- The skill's behavioural evals were not run.
- No license has been chosen.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
