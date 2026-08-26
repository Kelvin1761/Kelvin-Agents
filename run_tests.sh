#!/usr/bin/env bash
# Run every Wong Choi test suite — macOS / Linux / Git Bash / WSL.
#
#   ./run_tests.sh
#
# WHY each suite still gets its OWN python process:
# The module-name collision that used to make this MANDATORY is gone — the
# engines are now packages (`au_racing_engine` / `hkjc_racing_engine`), so both
# can be imported side by side in one interpreter. Separate processes are kept
# because the suites still differ in working directory and in the sys.path
# entries their non-engine helpers rely on, and because one suite crashing
# should not take the others' results with it.
set -uo pipefail
cd "$(dirname "$0")"
REPO_ROOT="$(pwd)"

if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

PY="${PYTHON_BIN:-python3}"
FAILED=()
PASSED=()

run_suite() {
  local label="$1" workdir="$2"
  shift 2
  echo ""
  echo "=============================================================="
  echo "  $label"
  echo "=============================================================="
  if ( cd "$workdir" && "$PY" -m pytest "$@" -q -p no:cacheprovider ); then
    PASSED+=("$label")
  else
    FAILED+=("$label")
  fi
}

run_suite "AU Wong Choi"        "$REPO_ROOT" .agents/skills/au_racing/au_wong_choi_auto/tests
run_suite "HKJC Wong Choi"      "$REPO_ROOT" .agents/skills/hkjc_racing/hkjc_wong_choi_auto/tests
run_suite "Shared racing"       "$REPO_ROOT" .agents/skills/shared_racing/tests
run_suite "Shared Wong Choi"   "$REPO_ROOT" .agents/skills/shared_wong_choi/tests
run_suite "Race compliance QA"  "$REPO_ROOT" .agents/skills/race_compliance_qa/tests
run_suite "NBA Wong Choi"       "$REPO_ROOT" \
  .agents/skills/nba/nba_wong_choi/tests \
  .agents/skills/nba/nba_daily_auto/tests \
  .agents/skills/nba/nba_reflector/tests
run_suite "Agent scripts"       "$REPO_ROOT" .agents/scripts/tests
run_suite "Dashboard (python)"  "$REPO_ROOT" Horse_Racing_Dashboard/tests Horse_Racing_Dashboard/backend/tests
run_suite "Tennis Wong Choi"    "$REPO_ROOT/tennis-wong-choi" tests

# Dashboard Cloudflare Functions + static template are node:test, not pytest.
if command -v node >/dev/null 2>&1; then
  echo ""
  echo "=============================================================="
  echo "  Dashboard (node)"
  echo "=============================================================="
  node_ok=1
  for t in Horse_Racing_Dashboard/tests/*.mjs; do
    [ -f "$t" ] || continue
    echo "--- $t"
    node "$t" | grep -E "^# (pass|fail)" || node_ok=0
    # shellcheck disable=SC2181
    if [ "${PIPESTATUS[0]}" -ne 0 ]; then node_ok=0; fi
  done
  if [ "$node_ok" -eq 1 ]; then PASSED+=("Dashboard (node)"); else FAILED+=("Dashboard (node)"); fi
else
  echo "!! node not found — skipped Dashboard (node) suite"
fi

echo ""
echo "=============================================================="
echo "  SUMMARY"
echo "=============================================================="
for s in "${PASSED[@]:-}"; do [ -n "$s" ] && echo "  PASS  $s"; done
for s in "${FAILED[@]:-}"; do [ -n "$s" ] && echo "  FAIL  $s"; done

if [ "${#FAILED[@]}" -gt 0 ]; then
  echo ""
  echo "${#FAILED[@]} suite(s) failed."
  exit 1
fi
echo ""
echo "All suites passed."
