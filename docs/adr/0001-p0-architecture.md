# ADR-0001 — P0 architecture decisions

Status: Proposed (PoC) · Date: 2026-11-09

Each decision lists the option chosen, what was rejected, and when to revisit.

## D1. A zero-dependency Python CLI is the single deterministic core

- **Chosen:** `eqk` package, stdlib only, Python ≥ 3.9. The Agent Skill, a future CI
  workflow, and a future Visual Git adapter all call the CLI or read its JSON.
- **Rejected:** Node CLI (Python is more often present on locked-down machines and is
  the primary language of the target users); shell scripts (no Windows, hard to
  test); MCP server / service (explicitly out of scope; adds runtime with no P0 need).
- **Revisit when:** a TypeScript-only team cannot run Python, or packaging is
  requested (P2).

## D2. Profiles are JSON data, not code

- Each check = tool + args + applicability + gate flag + exit-code mapping + install
  hint. One level of `extends`. Reviewable as diffs; no plugin system.
- **Rejected:** YAML (needs a dependency), Python plugins (code execution, harder to
  audit), a rule DSL.
- **Revisit when:** a profile needs logic that applicability conditions cannot express.

## D3. Adoption is create-only, manifest-backed, and reversible

- `apply` creates missing files only (`open(..., "x")`), records sha256 per file in
  `.quality/applied.json`; `revert` removes files whose hash matches.
- **Rejected:** merging into `pyproject.toml` / `package.json` (needs a
  round-tripping TOML/JSON editor and risks reformatting user files); a
  git-commit-based undo (doesn't work outside git, mixes with user changes).
- **Consequence:** an existing repo with its own config gets *no* config changes at
  all — eqk uses that config as-is. Settings eqk would like but can't add without
  editing are surfaced in `plan` instead.

## D4. Gate vs info checks; three-valued overall verdict

- Gate failure → `fail`. Info failure → `warning`. Overall is `pass` **only** if
  every applicable gate executed and passed; otherwise `incomplete` (or `fail`).
- `not_run` / `unavailable` can only carry `not_applicable` or `unknown`. Enforced
  twice: JSON Schema `if/then` and `verify.validate_invariants()` before writing.
- pytest exit 5 (no tests collected) maps to `unknown`, not pass.
- Formatting and type checking are info-only by default so adopting eqk on a legacy
  repo never forces a mass reformat or a typing project.

## D5. Tools are resolved, never installed

- Lookup order: repo `.venv`/`venv`, repo `node_modules/.bin`, then `PATH`. Missing
  tool → `unavailable` with an install hint. This *is* the offline / restricted mode;
  there is no separate flag.
- **Rejected:** auto-install via pip/npx (network, supply-chain and policy risk in
  enterprise environments; non-reproducible).

## D6. Report is versioned JSON + Markdown summary, privacy by construction

- `schema_version: "0.1"`; project id = hash of the root commit (else dir name);
  evidence logs redacted (repo path → `<repo>`, home → `~`, credential patterns).
- Reports and logs live in `.quality/{reports,evidence}` and are gitignored by a
  `.quality/.gitignore` that eqk creates (the repo's own `.gitignore` is untouched).

## D7. Things deliberately cut from P0

| Item from the brief | Decision | Reason |
|---|---|---|
| CI workflow generation | Deferred to P1 | Editing CI touches merge policy; P0 proves local adoption first |
| ESLint scaffolding for TS | Cut | Inventing lint rules for a JS codebase is opinionated; run it only if configured |
| Separate `--offline` flag | Merged into default behaviour | eqk never needs network |
| `disable` command | Merged into `revert` | Same operation |
| Vale / terminology / STE | P1, opt-in only | No P0 acceptance criterion depends on it |
| Property-based / contract testing | P1 | Needs real demand per repo |
