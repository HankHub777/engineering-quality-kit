# Tool survey and trade-offs (P0)

Principle: reuse mature tools; eqk only orchestrates and records evidence.
Versions are the ones exercised in the PoC run (docs/poc-evidence/environment.txt).

## Python

| Need | Chosen | Alternatives | Why |
|---|---|---|---|
| Lint | **ruff** 0.17 | flake8 + plugins, pylint | One fast binary, covers flake8/isort/pyupgrade; widely adopted. Cost: its defaults change between releases (observed: 0.17 default enabled `I` and `RUF100`), so eqk pins a rule set in new repos. |
| Format | **ruff format --check** (info) | black | Same binary; check-only, never applied. |
| Types | **mypy** (info) | pyright | Pure pip install, no Node. pyright is faster but needs Node. |
| Tests | **pytest** | unittest | De-facto standard; exit code 5 distinguishes "no tests". |

## TypeScript / JavaScript

| Need | Chosen | Alternatives | Why |
|---|---|---|---|
| Types | **tsc --noEmit** | — | Authoritative. Only runs if `tsconfig.json` exists. |
| Tests | **npm test** (the project's own script) | vitest/jest directly | Reuses whatever the project already runs; eqk doesn't pick a framework. |
| Lint | **eslint** (only if configured) | biome | ESLint config is project-specific; eqk does not invent one. Biome is a P1 candidate for new TS repos. |

## Docs

| Need | Chosen | Alternatives | Why |
|---|---|---|---|
| Markdown structure | **markdownlint-cli2** | remark-lint, mdformat | Common, config-light. eqk disables MD013 (line length) — style noise, breaks CJK prose. |
| Prose / terminology | **Vale** (opt-in) | textlint, LanguageTool | Vale supports custom vocabularies (term lists, STE-inspired rules) without claiming ASD-STE100 conformance. |

## Orchestration (not adopted)

| Option | Why not in P0 |
|---|---|
| pre-commit | Great runner, but installs hooks into `.git/hooks` and fetches tool repos over network; eqk preserves an existing `.pre-commit-config.yaml` and could emit one in P1. |
| MegaLinter / Super-Linter | Container-based, heavy, CI-first; poor fit for offline laptops. |
| tox / nox / just / make | Task runners, not adoption tools; projects can keep using them — `npm test`-style passthrough could be added. |
| SARIF as report format | Designed for static-analysis findings, not for "was this check executed"; eqk could *reference* SARIF output as evidence in P1. |
