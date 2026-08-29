#!/bin/zsh
# Transactional one-checkout launchd cutover for Central/HKJC/NBA/Tennis.
# AU is deliberately not reinstalled: this script is invoked by the AU
# Telegram poller itself, and booting out that label would kill activation.
set -eu

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h:h}"
AGENTS_DIR="${WC_LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
LAUNCHCTL="${WC_LAUNCHCTL_BIN:-launchctl}"
DOMAIN="gui/$(id -u)"
RUNTIME_CHECK="$PROJECT_ROOT/.agents/skills/shared_wong_choi/runtime_launchd.py"
TENNIS_RUNTIME_ROOT="${WC_TENNIS_RUNTIME_ROOT:-$HOME/Antigravity-repo/tennis-wong-choi}"

LABELS=(
  com.antigravity.hkjc-wong-choi.postrace
  com.antigravity.hkjc-wong-choi.prerace
  com.antigravity.hkjc-wong-choi.recovery
  com.antigravity.hkjc-wong-choi.startup
  com.antigravity.hkjc-wong-choi.watch
  com.antigravity.hkjc-wong-choi.weekly
  com.antigravity.nba-wong-choi.final-refresh
  com.antigravity.nba-wong-choi.health
  com.antigravity.nba-wong-choi.postgame
  com.antigravity.nba-wong-choi.production
  com.antigravity.nba-wong-choi.startup
  com.antigravity.nba-wong-choi.warmup
  com.antigravity.tennis-wong-choi.card
  com.antigravity.tennis-wong-choi.daily
  com.antigravity.tennis-wong-choi.recovery
  com.antigravity.central-wong-choi.durability
)
AU_LABELS=(
  com.antigravity.au-wong-choi.bot
  com.antigravity.au-wong-choi.evening
  com.antigravity.au-wong-choi.healthcheck
  com.antigravity.au-wong-choi.morning
)

snapshot_runtime() {
  local destination="$1"
  if [ -e "$destination" ] && [ -n "$(find "$destination" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    print -u2 -- "snapshot destination is not empty: $destination"
    return 1
  fi
  mkdir -p "$destination"
  for label in $LABELS; do
    local source="$AGENTS_DIR/$label.plist"
    [ ! -f "$source" ] || cp -p "$source" "$destination/$label.plist"
  done
  : > "$destination/.complete"
}

restore_runtime() {
  local source="$1"
  [ -f "$source/.complete" ] || {
    print -u2 -- "invalid runtime snapshot: $source"
    return 1
  }
  local failed=0
  mkdir -p "$AGENTS_DIR"
  for label in $LABELS; do
    local target="$AGENTS_DIR/$label.plist"
    "$LAUNCHCTL" bootout "$DOMAIN/$label" >/dev/null 2>&1 || true
    if [ -f "$source/$label.plist" ]; then
      cp -p "$source/$label.plist" "$target" || failed=1
      "$LAUNCHCTL" bootstrap "$DOMAIN" "$target" >/dev/null 2>&1 || failed=1
      "$LAUNCHCTL" enable "$DOMAIN/$label" >/dev/null 2>&1 || failed=1
    else
      rm -f "$target" || failed=1
    fi
  done
  return "$failed"
}

status_runtime() {
  local args=(
    "$RUNTIME_CHECK"
    --repo-root "$PROJECT_ROOT"
    --production-root "$PROJECT_ROOT"
  )
  if [ -n "${WC_LAUNCH_AGENTS_DIR:-}" ]; then
    args+=(--launch-agents-root "$AGENTS_DIR")
  fi
  [ "${WC_RUNTIME_NO_PROBE:-0}" != "1" ] || args+=(--no-probe)
  /usr/bin/python3 "${args[@]}"
}

case "${1:-}" in
  --snapshot)
    [ -n "${2:-}" ] || { print -u2 -- "--snapshot requires a directory"; exit 2; }
    snapshot_runtime "$2"
    exit 0
    ;;
  --restore)
    [ -n "${2:-}" ] || { print -u2 -- "--restore requires a directory"; exit 2; }
    restore_runtime "$2"
    exit $?
    ;;
  --status)
    status_runtime
    exit $?
    ;;
  "") ;;
  *) print -u2 -- "usage: $0 [--snapshot DIR|--restore DIR|--status]"; exit 2 ;;
esac

TZ_NAME="$(readlink /etc/localtime | sed 's#.*/zoneinfo/##')"
[ "$TZ_NAME" = "Australia/Sydney" ] || {
  print -u2 -- "local timezone is $TZ_NAME, not Australia/Sydney"
  exit 1
}

for script in \
  "$PROJECT_ROOT/.agents/skills/hkjc_racing/hkjc_daily_auto/install_macos_launchd.sh" \
  "$PROJECT_ROOT/.agents/skills/nba/nba_daily_auto/install_macos_launchd.sh" \
  "$PROJECT_ROOT/tennis-wong-choi/scripts/install_macos_launchd.sh" \
  "$PROJECT_ROOT/.agents/skills/central_wong_choi/install_macos_launchd.sh"; do
  [ -f "$script" ] || { print -u2 -- "missing installer: $script"; exit 1; }
done
[ -f "$TENNIS_RUNTIME_ROOT/tennis_wc.db" ] || {
  print -u2 -- "live Tennis database missing: $TENNIS_RUNTIME_ROOT/tennis_wc.db"
  exit 1
}
[ ! -f "$AGENTS_DIR/com.antigravity.nba-wong-choi.pregame.plist" ] || {
  print -u2 -- "legacy NBA pregame plist is still active; disable it before unified cutover"
  exit 1
}
/usr/bin/python3 -c 'import curl_cffi' || {
  print -u2 -- "system Python is missing curl_cffi required by Tennis"
  exit 1
}
/usr/bin/python3 - "$TENNIS_RUNTIME_ROOT/tennis_wc.db" <<'PY'
import sqlite3, sys
with sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True) as conn:
    result = conn.execute("PRAGMA quick_check(1)").fetchone()
if not result or result[0] != "ok":
    raise SystemExit(f"Tennis SQLite quick_check failed: {result}")
PY

# Refuse to boot out a live domain run. The Telegram poller is intentionally
# excluded because it is the caller and AU is not reinstalled.
if pgrep -f 'hkjc_daily_schedule.py|nba_daily_schedule.py|tennis_daily_schedule.py|tennis_card_recovery.py' >/dev/null 2>&1; then
  print -u2 -- "a HKJC/NBA/Tennis automation run is active; cutover deferred"
  exit 1
fi

# AU must already be on this checkout. This proves we can leave its bot loaded
# while the approval command completes.
for label in $AU_LABELS; do
  plist="$AGENTS_DIR/$label.plist"
  [ -f "$plist" ] || { print -u2 -- "missing AU runtime plist: $label"; exit 1; }
  /usr/bin/plutil -convert json -o - "$plist" \
    | grep -F "$PROJECT_ROOT/.agents/skills/au_racing/au_daily_auto/" \
      >/dev/null || {
        print -u2 -- "AU runtime is not on the activation checkout: $label"
        exit 1
      }
done

SNAPSHOT="$(mktemp -d -t wc-runtime-cutover)"
snapshot_runtime "$SNAPSHOT"
COMPLETED=0
cleanup() {
  local original_status=$?
  trap - EXIT HUP INT TERM
  if [ "$COMPLETED" -ne 1 ]; then
    print -u2 -- "runtime cutover failed; restoring previous launchd plists"
    restore_runtime "$SNAPSHOT" || print -u2 -- "CRITICAL: launchd plist restore failed"
  fi
  rm -rf -- "$SNAPSHOT"
  exit "$original_status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

/bin/bash "$PROJECT_ROOT/.agents/skills/hkjc_racing/hkjc_daily_auto/install_macos_launchd.sh"
/bin/bash "$PROJECT_ROOT/.agents/skills/nba/nba_daily_auto/install_macos_launchd.sh"
WC_TENNIS_RUNTIME_ROOT="$TENNIS_RUNTIME_ROOT" \
  TENNIS_LOG_DIR="$TENNIS_RUNTIME_ROOT/data/logs" \
  TENNIS_ANALYSIS_OUTPUT_ROOT="${TENNIS_ANALYSIS_OUTPUT_ROOT:-/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity}" \
  /bin/zsh "$PROJECT_ROOT/tennis-wong-choi/scripts/install_macos_launchd.sh"
/bin/zsh "$PROJECT_ROOT/.agents/skills/central_wong_choi/install_macos_launchd.sh"
status_runtime

COMPLETED=1
print -r -- "production runtime cutover verified: AU/HKJC/NBA/Tennis/Central aligned"
