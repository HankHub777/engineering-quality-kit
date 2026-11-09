#!/usr/bin/env bash
# Reproduce the PoC evidence in docs/poc-evidence/. Requires ruff, pytest, mypy, tsc, npm,
# markdownlint-cli2 on PATH (missing tools make the matching tests SKIP, which is recorded).
set -uo pipefail
KIT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$KIT/docs/poc-evidence"
mkdir -p "$OUT"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$KIT"

{
  echo "# environment"; date -u +%Y-%m-%dT%H:%M:%SZ; uname -sm; python3 --version
  for t in git ruff pytest mypy tsc node npm markdownlint-cli2; do
    printf '%-18s %s\n' "$t" "$($t --version 2>&1 | head -1 || echo MISSING)"; done
} > "$OUT/environment.txt"

(cd "$KIT" && python3 -m unittest -v tests.test_unit tests.test_acceptance) > "$OUT/test-run.txt" 2>&1
echo "unittest exit=$?" >> "$OUT/test-run.txt"

# Sample reports: pass, fail (injected defect), incomplete (skipped), unavailable (no tools).
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cp -R "$KIT/examples/python-existing" "$TMP/repo"
git -C "$TMP/repo" init -q -b main && git -C "$TMP/repo" add -A
git -C "$TMP/repo" -c user.name=poc -c user.email=poc@example.invalid commit -qm init
eqk() { python3 -m eqk "$@" "$TMP/repo"; }
eqk apply --profile python-data --yes > /dev/null
git -C "$TMP/repo" add -A && git -C "$TMP/repo" -c user.name=poc -c user.email=poc@example.invalid commit -qm "adopt eqk"
eqk verify > "$OUT/01-pass.txt"; echo "exit=$?" >> "$OUT/01-pass.txt"
cp "$TMP/repo/.quality/reports/latest.json" "$OUT/01-pass.json"
eqk verify --skip py.test > "$OUT/02-incomplete-skipped.txt"; echo "exit=$?" >> "$OUT/02-incomplete-skipped.txt"
cp "$TMP/repo/.quality/reports/latest.json" "$OUT/02-incomplete-skipped.json"
PATH=/usr/bin:/bin eqk verify > "$OUT/03-incomplete-unavailable.txt"; echo "exit=$?" >> "$OUT/03-incomplete-unavailable.txt"
cp "$TMP/repo/.quality/reports/latest.json" "$OUT/03-incomplete-unavailable.json"
printf 'import os\n' | cat - "$TMP/repo/inventory/stock.py" > "$TMP/s" && mv "$TMP/s" "$TMP/repo/inventory/stock.py"
eqk verify > "$OUT/04-fail-injected-defect.txt"; echo "exit=$?" >> "$OUT/04-fail-injected-defect.txt"
cp "$TMP/repo/.quality/reports/latest.json" "$OUT/04-fail-injected-defect.json"
git -C "$TMP/repo" checkout -q -- inventory/stock.py
git -C "$TMP/repo" reset -q --hard HEAD~1  # back to pre-adoption commit; files stay untracked-free
eqk apply --profile python-data --yes > /dev/null
eqk verify > /dev/null
eqk revert > "$OUT/05-revert.txt"; echo "exit=$?" >> "$OUT/05-revert.txt"
git -C "$TMP/repo" status --porcelain --ignored >> "$OUT/05-revert.txt"; echo "(empty status above = tree restored)" >> "$OUT/05-revert.txt"

# Dogfood: the kit verifies itself (verify-only, nothing written into the kit).
(cd "$KIT" && python3 -m eqk verify --profile python-data --out "$TMP/self" .) > "$OUT/06-self-check.txt" 2>/dev/null
echo "exit=$?" >> "$OUT/06-self-check.txt"
echo "evidence written to $OUT"
