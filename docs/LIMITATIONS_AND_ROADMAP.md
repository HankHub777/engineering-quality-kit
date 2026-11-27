# Known limitations, roadmap, and start conditions

## Known limitations (v0.1)

- **Report identifies a commit, not a tree.** If the working tree is dirty the report
  says so in `git.dirty` and `limitations`, but does not hash the exact content.
  (A content snapshot id is what the Visual Git / OpenDev Lens "stale review" rule
  would need — see P2.)
- **`minimal` adds no config**, so ruff runs with its installed defaults, which
  change between ruff releases. Pin ruff in the project, or use `python-data`.
- **Applicability is heuristic**: any `*.py` file makes Python checks applicable;
  a repo with a stray script will get Python gates. Use `--skip` or pick a profile.
- **The project's own test command may write files** (e.g. snapshots, coverage);
  eqk only redirects ruff/mypy/pytest caches.
- **No per-check config in `.quality/eqk.json` yet** (e.g. turn a gate into info).
- **Single-directory scope**: no monorepo / workspace awareness.
- **Redaction is best-effort** (path replacement + credential regexes).
- **Detection scope is narrow**: `tsconfig.json`, ESLint config (`eslint.config.*`,
  `.eslintrc*`) and `.markdownlint*` are detected at the repo top level only; an
  `"eslintConfig"` key in `package.json` is not detected (so `ts.lint` stays
  `not_applicable`).
- **Python 3.9/3.10 TOML fallback** (no `tomllib`) only recognises `[tool.ruff]`-style
  table headers; dotted keys such as `tool.ruff.line-length = 100` are missed.
- Skill evals are written, not executed.
- **Windows timeout kill reaches only the direct child.** On POSIX a timed-out (or
  interrupted) check's whole process group is killed; on Windows only the process eqk
  started is killed, so processes it started (e.g. node under `npm test`) can keep running.
- **Undoing an adoption with `git reset` leaves run outputs behind.** eqk's ignored run
  outputs (`.quality/evidence|reports|cache`) stay on disk; a later `apply` treats them as
  pre-existing and `revert` then keeps them (this fails toward keeping data). Remove them
  with `git clean -fdX .quality` (capital `-X` removes only ignored files) or by hand.

## Deliberately not built (per brief §10)

Web UI, database, MCP server, agent orchestrator, multi-tenancy, own linter/test
framework, auto merge/deploy, auto-install of tools.

## P1 candidates — start conditions

| Item | Start when |
|---|---|
| GitHub reusable workflow running `eqk verify` | P0 adopted in ≥ 2 real repos and their owners want CI gating; must not change branch protection without approval |
| Per-check overrides in `eqk.json` (gate ↔ info, extra args) | A real repo needs to adopt with a gate demoted |
| Schema 0.2: content snapshot id, check config hash | Visual Git adapter or stale-review work starts |
| Docs profile: Vale + glossary, STE-inspired rules | A team has delivery / operations docs that caused real errors |
| Property-based (Hypothesis / fast-check) and contract / data-quality checks | A specific repo has a bug class these would have caught |
| Biome for TS repos without ESLint | Repeated requests to add TS lint to new repos |
| Windows process-tree kill on timeout (`CREATE_NEW_PROCESS_GROUP` + `taskkill /T /F`) | A Windows CI runner exists |
| A/B evaluation of rules | ≥ 3 repos with history of eqk reports to compare |

## P2 candidates — start conditions

| Item | Start when |
|---|---|
| Read-only adapter for Visual Git / OpenDev Lens (reads `.quality/reports/latest.json`) | That tool has a P0 that renders a change review |
| Link evidence to commit / PR | CI workflow (P1) is in use |
| Cross-version quality comparison | Reports exist for many commits in one repo |
| Guided install via guided-local-workbench-template | A Workbench user asks for it; adapter stays optional |
| PyPI package / standalone binary | Users can't run from source |
