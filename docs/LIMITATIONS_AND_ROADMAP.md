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
- Skill evals are written, not executed.

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
| A/B evaluation of rules | ≥ 3 repos with history of eqk reports to compare |

## P2 candidates — start conditions

| Item | Start when |
|---|---|
| Read-only adapter for Visual Git / OpenDev Lens (reads `.quality/reports/latest.json`) | That tool has a P0 that renders a change review |
| Link evidence to commit / PR | CI workflow (P1) is in use |
| Cross-version quality comparison | Reports exist for many commits in one repo |
| Guided install via guided-local-workbench-template | A Workbench user asks for it; adapter stays optional |
| PyPI package / standalone binary | Users can't run from source |
