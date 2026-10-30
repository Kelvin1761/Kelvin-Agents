#!/bin/zsh
set -eu

SCRIPT_DIR="${0:A:h}/scripts"
SKILL_DIR="${SCRIPT_DIR:h}"
PROJECT_ROOT="${SKILL_DIR:h:h:h}"

if [ "${1:-}" != "--render-only" ] && [ "${1:-}" != "--status" ]; then
  CUTOVER_REPO="$PROJECT_ROOT"
  LEASE_HELPER="$CUTOVER_REPO/.agents/skills/shared_wong_choi/runtime_cutover_lease.py"
  if [ -z "${WC_RUNTIME_CUTOVER_FD:-}" ]; then
    exec /usr/bin/python3 "$LEASE_HELPER" --mode exclusive -- /bin/zsh "$0" "$@"
  fi
  /usr/bin/python3 "$LEASE_HELPER" --mode exclusive --verify || exit $?
fi

if [ -n "${WC_RUNTIME_INSTALL_SNAPSHOT:-}" ] && [ "${1:-}" != "--render-only" ] && [ "${1:-}" != "--status" ]; then
  [ "$#" -eq 0 ] || { echo "bound installation accepts no alternate mode" >&2; exit 2; }
  . "$CUTOVER_REPO/.agents/skills/shared_wong_choi/runtime_install_journal.sh"
fi

LABEL="com.antigravity.central-wong-choi.durability"
DEST="${WC_LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}/$LABEL.plist"
UID_NUM="$(id -u)"

render_durability() {
  sed -e "s#__SCRIPT_DIR__#$SCRIPT_DIR#g" -e "s#__PROJECT_ROOT__#$PROJECT_ROOT#g" \
    "$SKILL_DIR/launchd/$LABEL.plist.template" > "$1"
  chmod 644 "$1"
}

case "${1:-}" in
  --render-only)
    [ "$#" -eq 2 ] && [ -n "$2" ] || exit 2
    mkdir -p "$2"
    render_durability "$2/$LABEL.plist"
    if [ "${WC_INSTALL_RESEARCH_REVIEW:-0}" = "1" ]; then
      /bin/zsh "$SKILL_DIR/install_research_review.sh" --render-only "$2"
    fi
    exit 0
    ;;
  --status)
    launchctl print "gui/$UID_NUM/$LABEL" 2>/dev/null \
      | grep -E "state =|last exit code|program =|runs =" || print -r -- "(未安裝)"
    exit 0
    ;;
  --uninstall)
    launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
    rm -f "$DEST"
    print -r -- "已移除 $LABEL"
    exit 0
    ;;
esac

TZ_NAME="$(readlink /etc/localtime | sed 's#.*/zoneinfo/##')"
if [ "$TZ_NAME" != "Australia/Sydney" ]; then
  print -r -- "本機時區係 ${TZ_NAME}，唔係 Australia/Sydney；拒絕安裝。" >&2
  exit 1
fi

mkdir -p "${WC_LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}" "$SCRIPT_DIR/logs"
chmod +x "$SCRIPT_DIR/central_daily_maintenance.py" \
  "$SCRIPT_DIR/run_central_daily_maintenance.sh"
if [ -n "${WC_RUNTIME_INSTALL_SNAPSHOT:-}" ]; then
  wc_runtime_journal "$WC_RUNTIME_INSTALL_SNAPSHOT" begin-job "$LABEL"
  wc_runtime_journal "$WC_RUNTIME_INSTALL_SNAPSHOT" publish-job "$LABEL"
else
  render_durability "$DEST"
fi
"${WC_LAUNCHCTL_BIN:-launchctl}" bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
"${WC_LAUNCHCTL_BIN:-launchctl}" bootstrap "gui/$UID_NUM" "$DEST"
"${WC_LAUNCHCTL_BIN:-launchctl}" enable "gui/$UID_NUM/$LABEL"
print -r -- "已安裝 ${LABEL}：每日悉尼時間 03:20 D1 verified backup；失敗會喺 05:20 自動補跑"
# Unified cutover owns the snapshot/rollback for both Central labels. Ordinary
# durability installation must not implicitly initialize research state.
if [ "${WC_INSTALL_RESEARCH_REVIEW:-0}" = "1" ]; then
  /bin/zsh "$SKILL_DIR/install_research_review.sh"
fi
