---
name: quality-adoption
description: Add, check, or remove lint/type/test quality gates in a Python, TypeScript or docs repository using engineering-quality-kit (eqk), with evidence-backed results. Use when asked to "set up quality checks", "add linting/tests to this repo", "is this repo passing its checks", or to adopt quality tooling in an existing project without breaking its setup. Not for writing the tests themselves or fixing the lint findings.
metadata:
  version: 0.1.0
  requires: eqk >= 0.1.0 (python -m eqk), Python 3.9+
---

# Quality adoption

`eqk` does the deterministic work (detect, plan, create files, run tools, write the report).
Your job is judgment: pick a profile, read the plan, explain trade-offs, and report
the evidence honestly.

## Hard rules (the contract — everything else is your call)

1. Run `eqk inspect` before changing anything. Do not apply on a dirty working tree
   unless the user agrees; eqk's changes should be reviewable on their own.
2. Show the user the `eqk plan` output and get a go-ahead before `eqk apply --yes`.
3. Report verification exactly as the JSON report says. `incomplete`, `unavailable`,
   `not_run` and `unknown` are **not** passes; never summarize them as "checks pass".
4. Do not install tools, reformat code, delete existing tests/rules, or edit CI or
   merge settings as part of adoption. If one of those would help, propose it as a
   separate step with its impact.
5. Do not paste report content containing paths or secrets into public places; the
   report is already redacted, raw tool output may not be.

## Commands

```bash
python -m eqk inspect [PATH] [--json]
python -m eqk plan    [PATH] --profile {minimal|python-data|typescript-web|docs} [--json]
python -m eqk apply   [PATH] --profile NAME --yes
python -m eqk verify  [PATH] [--profile NAME] [--skip ids] [--only ids] [--json]
python -m eqk revert  [PATH]
```

Exit codes: 0 pass · 1 gate failed · 2 incomplete · 3 not applied · 4 usage/state error.

## Choosing a profile

`inspect` suggests one. Prefer `minimal` for an existing repo with no prior gates
(progressive adoption); a language profile adds non-blocking (`info`) signals.
If a gate tool is missing, say which and give the install hint from the report;
offline or locked-down environments are expected — report, don't work around.

## Reading results

- Overall `fail`: list the failing gate checks with their first errors and the
  evidence log path (`.quality/evidence/<run>/<check>.log`).
- Overall `incomplete`: name each gate without a passing result and why
  (`unavailable` tool, `not_run` by `--skip`, `unknown` e.g. no tests collected).
- `warning` comes from non-gate checks (format, types); mention, don't block.

## Undo

`eqk revert` removes exactly the files eqk created. Files a human edited after apply
are kept unless `--force`; tell the user which ones.
