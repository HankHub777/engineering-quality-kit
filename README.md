# engineering-quality-kit (eqk) — v0.1 PoC

Low-friction quality adoption for new **and existing** repositories, with
evidence-backed results. eqk does not lint or test anything itself: it detects what a
repo already has, adds the minimum config needed, runs the mature tools you already
use (ruff, pytest, mypy, tsc, npm test, markdownlint), and writes a versioned JSON
report in which **nothing un-run is ever reported as passed**.

> Status: P0 proof of concept. See [docs/POC_REPORT.md](docs/POC_REPORT.md) for what is
> verified and what is not.

## Quick start

Requires Python ≥ 3.9 and git. No dependencies. eqk never installs tools.

```bash
python -m eqk inspect PATH                         # read-only
python -m eqk plan    PATH --profile python-data   # what would change (diff), nothing written
python -m eqk apply   PATH --profile python-data --yes
python -m eqk verify  PATH                         # report -> PATH/.quality/reports/latest.json
python -m eqk revert  PATH                         # remove exactly what apply created
```

(Or `pip install .` and use `eqk …`.) Run from this repo, or set `PYTHONPATH` to it.

| Exit code | Meaning |
|---|---|
| 0 | pass — every applicable gate check executed and passed |
| 1 | fail — at least one gate check failed |
| 2 | incomplete — no failure, but some gate has no passing evidence (tool missing, skipped, no tests) |
| 3 | apply without `--yes`: plan printed, nothing written |
| 4 | usage / state error (e.g. already applied, revert kept edited files) |

## Profiles

| Profile | Gate checks (block) | Info checks (warn only) | May create |
|---|---|---|---|
| `minimal` | `py.lint` ruff · `py.test` pytest · `ts.typecheck` tsc · `js.test` npm test | — | — |
| `python-data` | minimal | `py.format` ruff format --check · `py.types` mypy | `ruff.toml` if no ruff config exists |
| `typescript-web` | minimal | `ts.lint` eslint (only if the repo already configures ESLint) | — |
| `docs` | `docs.markdownlint` | `docs.vale` (only if `.vale.ini` exists) | `.markdownlint.jsonc` if none exists |

Checks only run when applicable (language present, required config present).
Every apply also creates `.quality/eqk.json`, `.quality/.gitignore`, and the
manifest `.quality/applied.json`.

## Safety contract for existing repos

- `inspect` and `plan` write nothing. `apply` needs `--yes`.
- `apply` only **creates** files that don't exist (opened with exclusive-create). It
  never edits, reformats, or deletes existing files, CI, pre-commit, or merge policy.
- `verify` keeps tool caches in `.quality/cache/` and writes nothing into an
  un-adopted repo (report goes to a temp dir or `--out`).
- `revert` deletes only files whose hash still matches what apply wrote; edited
  files are kept and listed.
- Reports contain a hashed project id, never paths; tool output is redacted for
  local paths and common credential shapes before it is written.

## Layout

```text
eqk/                CLI (inspect, plan, apply, verify, revert), profiles/, templates/
schema/             quality-result.v0.1.schema.json — the data contract
skills/quality-adoption/   Agent Skill + eval cases
examples/           python-new, python-existing, typescript-web, docs-basic
tests/              unit + P0 acceptance tests (real tools, temp git repos)
scripts/poc_evidence.sh    regenerates docs/poc-evidence/
docs/               ADRs, tool survey, PoC report, limitations, roadmap
```

## Running the tests

```bash
python -m unittest -v tests.test_unit tests.test_acceptance
```

Acceptance tests need ruff, pytest, mypy, tsc, node/npm and markdownlint-cli2 on
`PATH`; a missing tool makes the matching test **skip** with the reason.

## License

[Apache License 2.0](LICENSE). Contributions are accepted under the same
license (Apache-2.0 §5).
