#!/bin/zsh
# One-time bridge: let the candidate bot receive the first /approve command
# before production itself contains the governance command.
set -eu

SELECTOR="${1:-}"
[[ "$SELECTOR" =~ '^[0-9a-f]{12,64}$' ]] || {
  print -u2 -- "usage: $0 <12-or-more lowercase commit SHA>"
  exit 2
}

SCRIPT_DIR="${0:A:h}"
CANDIDATE_ROOT="${SCRIPT_DIR:h:h:h}"
PRODUCTION_ROOT="${WC_PRODUCTION_ROOT:-$HOME/wongchoi-scheduler}"
STATE_ROOT="${WONGCHOI_CONTROL_STATE_ROOT:-$HOME/WongChoiData/WongChoiControl}"
BOT="${WC_BOOTSTRAP_BOT:-$CANDIDATE_ROOT/.agents/skills/au_racing/au_daily_auto/au_telegram_bot.py}"
NOTIFIER="${WC_BOOTSTRAP_NOTIFIER:-$CANDIDATE_ROOT/.agents/skills/shared_racing/scripts/racing_telegram.py}"
STATUS_CLI="${WC_BOOTSTRAP_STATUS_CLI:-$CANDIDATE_ROOT/.agents/skills/central_wong_choi/scripts/central_wong_choi.py}"
OFFSET_FILE="$PRODUCTION_ROOT/.agents/skills/au_racing/au_daily_auto/logs/telegram_offset.json"
LABEL="com.antigravity.au-wong-choi.bot"
DOMAIN="gui/$(id -u)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
NOTIFY_ENV="$HOME/.wongchoi_notify.env"
LAUNCHCTL="${WC_LAUNCHCTL_BIN:-launchctl}"
MAX_ATTEMPTS="${WC_BOOTSTRAP_MAX_ATTEMPTS:-150}"
SLEEP_SECONDS="${WC_BOOTSTRAP_SLEEP_SECONDS:-2}"

[ -f "$BOT" ] || { print -u2 -- "candidate bot missing: $BOT"; exit 1; }
[ -f "$PLIST" ] || { print -u2 -- "production bot plist missing: $PLIST"; exit 1; }
[ -e "$PRODUCTION_ROOT/.git" ] || {
  print -u2 -- "production checkout missing: $PRODUCTION_ROOT"
  exit 1
}
[ -f "$NOTIFY_ENV" ] && source "$NOTIFY_ENV"
[ -n "${WC_NOTIFY_TELEGRAM_TOKEN:-}" ] && [ -n "${WC_NOTIFY_TELEGRAM_CHAT:-}" ] || {
  print -u2 -- "Telegram credentials are not configured"
  exit 1
}

restore_poller() {
  local rc=$?
  trap - EXIT HUP INT TERM
  "$LAUNCHCTL" bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  "$LAUNCHCTL" bootstrap "$DOMAIN" "$PLIST" >/dev/null 2>&1 || rc=1
  "$LAUNCHCTL" enable "$DOMAIN/$LABEL" >/dev/null 2>&1 || rc=1
  exit "$rc"
}
trap restore_poller EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

"$LAUNCHCTL" bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true

/usr/bin/python3 "$NOTIFIER" --message \
  "🔐 中央旺財首次 approval window 已開\n請於5分鐘內發：/approve ${SELECTOR}" \
  --json >/dev/null

export WC_PRIMARY_REPO_ROOT="$CANDIDATE_ROOT"
export WC_AU_PRODUCTION_ROOT="$PRODUCTION_ROOT"
export WC_HKJC_PRODUCTION_ROOT="$PRODUCTION_ROOT"
export WC_TENNIS_PRODUCTION_ROOT="$PRODUCTION_ROOT"
export WC_NBA_PRODUCTION_ROOT="$PRODUCTION_ROOT"
export WC_TELEGRAM_OFFSET_FILE="$OFFSET_FILE"
export WONGCHOI_CONTROL_STATE_ROOT="$STATE_ROOT"

for (( attempt = 1; attempt <= MAX_ATTEMPTS; attempt++ )); do
  /usr/bin/python3 "$BOT"
  head="$(git -C "$PRODUCTION_ROOT" rev-parse HEAD 2>/dev/null || true)"
  status_output="$(/usr/bin/python3 \
    "$STATUS_CLI" \
    --repo "$CANDIDATE_ROOT" --state-root "$STATE_ROOT" status 2>/dev/null || true)"
  if [[ "$head" == "$SELECTOR"* ]] \
    && print -r -- "$status_output" | grep -F "Release：${SELECTOR[1,12]} · merged · activate succeeded" >/dev/null; then
    /usr/bin/python3 "$NOTIFIER" --message \
      "✅ 首次 approval handoff 完成 ${SELECTOR[1,12]}；production poller 已接管" \
      --json >/dev/null || true
    exit 0
  fi
  if print -r -- "$status_output" | grep -F "Release：${SELECTOR[1,12]} · merged · activate failed" >/dev/null; then
    print -u2 -- "activation failed; see Central release event"
    exit 1
  fi
  sleep "$SLEEP_SECONDS"
done

print -u2 -- "approval window timed out; production poller will be restored"
exit 1
