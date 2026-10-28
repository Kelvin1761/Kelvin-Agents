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
TENNIS_PYTHON_BIN="${TENNIS_PYTHON_BIN:-$TENNIS_RUNTIME_ROOT/.venv/bin/python}"
TENNIS_DB_POINTER="${WC_TENNIS_DB_POINTER:-$HOME/.wongchoi_tennis_db}"
SNAPSHOT_STATE="$PROJECT_ROOT/.agents/skills/shared_wong_choi/runtime_snapshot_state.py"

LABELS=(
  com.antigravity.hkjc-wong-choi.intraday
  com.antigravity.hkjc-wong-choi.lineup
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
  com.antigravity.tennis-wong-choi.preclose
  com.antigravity.central-wong-choi.durability
  com.antigravity.central-wong-choi.research-review
)
AU_LABELS=(
  com.antigravity.au-wong-choi.bot
  com.antigravity.au-wong-choi.evening
  com.antigravity.au-wong-choi.healthcheck
  com.antigravity.au-wong-choi.morning
)

snapshot_pointer() {
  local destination="$1"
  [[ "$TENNIS_DB_POINTER" == /* && "$TENNIS_DB_POINTER" != *$'\n'* ]] || return 1
  if [ -L "$TENNIS_DB_POINTER" ] || { [ -e "$TENNIS_DB_POINTER" ] && [ ! -f "$TENNIS_DB_POINTER" ]; }; then
    print -u2 -- "unsafe Tennis DB pointer"
    return 1
  fi
  if [ -f "$TENNIS_DB_POINTER" ]; then
    [ "$(wc -c < "$TENNIS_DB_POINTER")" -le 4096 ] || return 1
    cp -p "$TENNIS_DB_POINTER" "$destination/.tennis-db-pointer-original" || return 1
    cmp -s "$TENNIS_DB_POINTER" "$destination/.tennis-db-pointer-original" || return 1
  fi
  print -r -- "$TENNIS_DB_POINTER" > "$destination/.tennis-db-pointer-path" || return 1
  print -r -- "$TENNIS_RUNTIME_ROOT/tennis_wc.db" > "$destination/.tennis-db-pointer-candidate" || return 1
}

restore_pointer() {
  local source="$1" bound restore_tmp item
  # Older snapshots predate pointer coverage; never infer their prior value.
  if [ ! -e "$source/.tennis-db-pointer-path" ] && [ ! -L "$source/.tennis-db-pointer-path" ]; then
    return 0
  fi
  for item in path candidate; do
    [ -f "$source/.tennis-db-pointer-$item" ] && [ ! -L "$source/.tennis-db-pointer-$item" ] || return 1
    [ "$(wc -c < "$source/.tennis-db-pointer-$item")" -le 4096 ] || return 1
  done
  IFS= read -r bound < "$source/.tennis-db-pointer-path"
  [ "$bound" = "$TENNIS_DB_POINTER" ] || return 1
  if [ -e "$source/.tennis-db-pointer-original" ] || [ -L "$source/.tennis-db-pointer-original" ]; then
    [ -f "$source/.tennis-db-pointer-original" ] && [ ! -L "$source/.tennis-db-pointer-original" ] || return 1
    [ "$(wc -c < "$source/.tennis-db-pointer-original")" -le 4096 ] || return 1
  fi
  [ ! -L "$TENNIS_DB_POINTER" ] || return 1
  if [ -e "$TENNIS_DB_POINTER" ]; then
    [ -f "$TENNIS_DB_POINTER" ] || return 1
    [ "$(wc -c < "$TENNIS_DB_POINTER")" -le 4096 ] || return 1
    if [ -f "$source/.tennis-db-pointer-original" ] && cmp -s "$TENNIS_DB_POINTER" "$source/.tennis-db-pointer-original"; then
      return 0
    fi
    cmp -s "$TENNIS_DB_POINTER" "$source/.tennis-db-pointer-candidate" || {
      print -u2 -- "Tennis DB pointer rollback blocked: concurrent change"
      return 1
    }
    if [ -f "$source/.tennis-db-pointer-original" ]; then
      [ ! -L "$source/.tennis-db-pointer-original" ] || return 1
      restore_tmp="$(mktemp "${TENNIS_DB_POINTER}.restore.XXXXXX")" || return 1
      cp -p "$source/.tennis-db-pointer-original" "$restore_tmp" || { rm -f -- "$restore_tmp"; return 1; }
      mv -f -- "$restore_tmp" "$TENNIS_DB_POINTER" || { rm -f -- "$restore_tmp"; return 1; }
    else
      rm -f -- "$TENNIS_DB_POINTER" || return 1
    fi
  elif [ -f "$source/.tennis-db-pointer-original" ]; then
    print -u2 -- "Tennis DB pointer rollback blocked: concurrent removal"
    return 1
  fi
  return 0
}

runtime_state() {
  local mode="$1" snapshot="$2" job="${3:-}" label
  local args=(--mode "$mode" --snapshot "$snapshot" --agents "$AGENTS_DIR"
    --launchctl "$LAUNCHCTL" --domain "$DOMAIN")
  for label in $LABELS; do
    args+=(--label "$label")
  done
  [ -z "$job" ] || args+=(--job "$job")
  /usr/bin/python3 "$SNAPSHOT_STATE" "${args[@]}"
}

snapshot_runtime() {
  local destination="$1"
  if [ -L "$destination" ] || { [ -e "$destination" ] && [ ! -d "$destination" ]; }; then
    print -u2 -- "unsafe snapshot destination"
    return 1
  fi
  if [ -e "$destination" ] && [ -n "$(find "$destination" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    print -u2 -- "snapshot destination is not empty: $destination"
    return 1
  fi
  mkdir -p "$destination"
  snapshot_pointer "$destination" || return 1
  for label in $LABELS; do
    local source="$AGENTS_DIR/$label.plist"
    if [ -L "$source" ] || { [ -e "$source" ] && [ ! -f "$source" ]; }; then
      print -u2 -- "unsafe installed runtime plist: $label"
      return 1
    fi
    [ ! -f "$source" ] || cp -p "$source" "$destination/$label.plist"
  done
  runtime_state capture "$destination" || return 1
  : > "$destination/.complete"
}

restore_runtime() {
  local source="$1"
  [ -f "$source/.complete" ] || {
    print -u2 -- "invalid runtime snapshot: $source"
    return 1
  }
  local failed=0 comparison=0 job_state was_loaded was_disabled changed_labels current_loaded
  # A preflight deferral did not change external state. Recovery must not
  # bootout live jobs just because the controller invokes --restore.
  if runtime_state unchanged "$source"; then
    restore_pointer "$source" || return 1
    print -r -- "launchd state unchanged; no launchd mutation"
    return 0
  else
    comparison=$?
  fi
  [ "$comparison" -eq 2 ] || return 1
  changed_labels="$(runtime_state changed-jobs "$source")" || return 1
  restore_pointer "$source" || return 1
  mkdir -p "$AGENTS_DIR"
  # Unchanged labels may own an active domain run. Never stop them merely
  # because another label needs recovery.
  for label in ${(f)changed_labels}; do
    local target="$AGENTS_DIR/$label.plist"
    job_state="$(runtime_state job-state "$source" "$label")" || return 1
    was_loaded="${job_state%% *}"
    was_disabled="${job_state##* }"
    current_loaded="$(runtime_state loaded-now "$source" "$label")" || return 1
    if [ "$current_loaded" -eq 1 ]; then
      if ! "$LAUNCHCTL" bootout "$DOMAIN/$label" >/dev/null 2>&1; then
        failed=1
        continue
      fi
    fi
    if [ -f "$source/$label.plist" ]; then
      if ! cp -p "$source/$label.plist" "$target"; then
        failed=1
        continue
      fi
      if [ "$was_loaded" -eq 1 ]; then
        if ! "$LAUNCHCTL" enable "$DOMAIN/$label" >/dev/null 2>&1; then
          failed=1
          continue
        fi
        "$LAUNCHCTL" bootstrap "$DOMAIN" "$target" >/dev/null 2>&1 || failed=1
      fi
    else
      rm -f "$target" || failed=1
    fi
    if [ "$was_disabled" -eq 1 ]; then
      "$LAUNCHCTL" disable "$DOMAIN/$label" >/dev/null 2>&1 || failed=1
    else
      "$LAUNCHCTL" enable "$DOMAIN/$label" >/dev/null 2>&1 || failed=1
    fi
  done
  runtime_state unchanged "$source" || failed=1
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
  if [ "${WC_ALLOW_AU_BOT_UNLOADED:-0}" = "1" ]; then
    args+=(--allow-unloaded-label com.antigravity.au-wong-choi.bot)
  fi
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
[ -x "$TENNIS_PYTHON_BIN" ] || {
  print -u2 -- "Tennis runtime interpreter is missing: $TENNIS_PYTHON_BIN"
  exit 1
}
# Reject an unsafe NBA polling cadence before snapshotting or touching any plist.
print -r -- "runtime cutover stage: NBA result timer preflight"
/usr/bin/python3 "$PROJECT_ROOT/.agents/skills/nba/nba_daily_auto/verify_results_timer.py" \
  "$PROJECT_ROOT/.agents/skills/nba/nba_daily_auto/launchd/com.antigravity.nba-wong-choi.postgame.plist.template"
print -r -- "runtime cutover stage: interpreter preflight"
"$TENNIS_PYTHON_BIN" -c 'import curl_cffi' || {
  print -u2 -- "Tennis runtime interpreter is missing curl_cffi: $TENNIS_PYTHON_BIN"
  exit 1
}
print -r -- "runtime cutover stage: SQLite preflight"
/usr/bin/python3 - "$TENNIS_RUNTIME_ROOT/tennis_wc.db" <<'PY'
import sqlite3, sys
with sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True) as conn:
    result = conn.execute("PRAGMA quick_check(1)").fetchone()
if not result or result[0] != "ok":
    raise SystemExit(f"Tennis SQLite quick_check failed: {result}")
PY

# Refuse to boot out a live domain run. The Telegram poller is intentionally
# excluded because it is the caller and AU is not reinstalled.
print -r -- "runtime cutover stage: active-run preflight"
if pgrep -f '(^|/)([Pp]ython[0-9.]*)([[:space:]]+-[A-Za-z]+)*[[:space:]]+[^[:space:]]*/(hkjc_daily_schedule.py|nba_daily_schedule.py|tennis_daily_schedule.py|tennis_card_recovery.py)([[:space:]]|$)' >/dev/null 2>&1; then
  print -u2 -- "a HKJC/NBA/Tennis automation run is active; cutover deferred"
  exit 1
fi

# AU must already be on this checkout. This proves we can leave its bot loaded
# while the approval command completes.
print -r -- "runtime cutover stage: AU preflight"
for label in $AU_LABELS; do
  plist="$AGENTS_DIR/$label.plist"
  [ -f "$plist" ] || { print -u2 -- "missing AU runtime plist: $label"; exit 1; }
  /usr/bin/plutil -convert json -o - "$plist" \
    | /usr/bin/python3 -c '
import json, sys
payload = json.load(sys.stdin)
expected = sys.argv[1]
values = [str(value) for value in payload.get("ProgramArguments") or []]
working = payload.get("WorkingDirectory")
if working:
    values.append(str(working))
raise SystemExit(0 if any(value.startswith(expected) for value in values) else 1)
' "$PROJECT_ROOT/.agents/skills/au_racing/au_daily_auto/" || {
        print -u2 -- "AU runtime is not on the activation checkout: $label"
        exit 1
      }
done

print -r -- "runtime cutover stage: snapshot"
SNAPSHOT="$(mktemp -d -t wc-runtime-cutover)"
snapshot_runtime "$SNAPSHOT"
COMPLETED=0
POINTER_TMP=""
cleanup() {
  local original_status=$?
  trap - EXIT HUP INT TERM
  if [ "$COMPLETED" -ne 1 ]; then
    print -u2 -- "runtime cutover failed; restoring previous launchd plists"
    restore_runtime "$SNAPSHOT" || print -u2 -- "CRITICAL: launchd plist restore failed"
  fi
  [ -z "$POINTER_TMP" ] || rm -f -- "$POINTER_TMP"
  rm -rf -- "$SNAPSHOT"
  exit "$original_status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# Publish configuration only after every preflight and with rollback armed.
if [ -f "$SNAPSHOT/.tennis-db-pointer-original" ]; then
  cmp -s "$TENNIS_DB_POINTER" "$SNAPSHOT/.tennis-db-pointer-original" || exit 1
else
  [ ! -e "$TENNIS_DB_POINTER" ] && [ ! -L "$TENNIS_DB_POINTER" ] || exit 1
fi
POINTER_TMP="$(mktemp "${TENNIS_DB_POINTER}.publish.XXXXXX")"
cp "$SNAPSHOT/.tennis-db-pointer-candidate" "$POINTER_TMP"
chmod 644 "$POINTER_TMP"
mv -f -- "$POINTER_TMP" "$TENNIS_DB_POINTER"

print -r -- "runtime cutover stage: HKJC installer"
/bin/bash "$PROJECT_ROOT/.agents/skills/hkjc_racing/hkjc_daily_auto/install_macos_launchd.sh"
print -r -- "runtime cutover stage: NBA installer"
/bin/bash "$PROJECT_ROOT/.agents/skills/nba/nba_daily_auto/install_macos_launchd.sh"
print -r -- "runtime cutover stage: Tennis installer"
WC_TENNIS_RUNTIME_ROOT="$TENNIS_RUNTIME_ROOT" \
  TENNIS_PYTHON_BIN="$TENNIS_PYTHON_BIN" \
  TENNIS_LOG_DIR="$TENNIS_RUNTIME_ROOT/data/logs" \
  TENNIS_ANALYSIS_OUTPUT_ROOT="${TENNIS_ANALYSIS_OUTPUT_ROOT:-/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity}" \
  /bin/zsh "$PROJECT_ROOT/tennis-wong-choi/scripts/install_macos_launchd.sh"
print -r -- "runtime cutover stage: Central installer"
WC_INSTALL_RESEARCH_REVIEW=1 \
  WC_LAUNCH_AGENTS_DIR="$AGENTS_DIR" WC_LAUNCHCTL_BIN="$LAUNCHCTL" \
  /bin/zsh "$PROJECT_ROOT/.agents/skills/central_wong_choi/install_macos_launchd.sh"
print -r -- "runtime cutover stage: calendar verification"
/usr/bin/python3 "$PROJECT_ROOT/.agents/skills/central_wong_choi/scripts/verify_research_calendar.py" \
  --template "$PROJECT_ROOT/.agents/skills/central_wong_choi/launchd/com.antigravity.central-wong-choi.research-review.plist.template" \
  --installed "$AGENTS_DIR/com.antigravity.central-wong-choi.research-review.plist"
print -r -- "runtime cutover stage: loaded runtime verification"
status_runtime

COMPLETED=1
print -r -- "production runtime cutover verified: AU/HKJC/NBA/Tennis/Central aligned"
