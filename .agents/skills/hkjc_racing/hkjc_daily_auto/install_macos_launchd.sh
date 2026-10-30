#!/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "${1:-}" != "--render-only" ] && [ "${1:-}" != "--status" ]; then
  CUTOVER_REPO="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
  LEASE_HELPER="$CUTOVER_REPO/.agents/skills/shared_wong_choi/runtime_cutover_lease.py"
  if [ -z "${WC_RUNTIME_CUTOVER_FD:-}" ]; then
    exec /usr/bin/python3 "$LEASE_HELPER" --mode exclusive -- /bin/bash "$0" "$@"
  fi
  /usr/bin/python3 "$LEASE_HELPER" --mode exclusive --verify || exit $?
fi

if [ -n "${WC_RUNTIME_INSTALL_SNAPSHOT:-}" ] && [ "${1:-}" != "--render-only" ] && [ "${1:-}" != "--status" ]; then
  [ "$#" -eq 0 ] || { echo "bound installation accepts no alternate mode" >&2; exit 2; }
  . "$CUTOVER_REPO/.agents/skills/shared_wong_choi/runtime_install_journal.sh"
fi

RUNNER="$SCRIPT_DIR/run_hkjc_daily_schedule.sh"
LOG_DIR="$SCRIPT_DIR/logs"
AGENTS_DIR="${WC_LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"

RENDER_ONLY=0
case "${1:-}" in
  --render-only)
    [ "$#" -eq 2 ] && [ -n "$2" ] || exit 2
    AGENTS_DIR="$2"
    RENDER_ONLY=1
    ;;
  "") ;;
  *) echo "Usage: $0 [--render-only DEST]" >&2; exit 2 ;;
esac
mkdir -p "$AGENTS_DIR"
if [ "$RENDER_ONLY" -eq 0 ]; then
  mkdir -p "$LOG_DIR"
  chmod +x "$RUNNER"
fi

for template in "$SCRIPT_DIR"/launchd/*.plist.template; do
  name="$(basename "$template" .template)"
  target="$AGENTS_DIR/$name"
  label="${name%.plist}"
  if [ "$RENDER_ONLY" -eq 0 ] && [ -n "${WC_RUNTIME_INSTALL_SNAPSHOT:-}" ]; then
    wc_runtime_journal "$WC_RUNTIME_INSTALL_SNAPSHOT" begin-job "$label"
    wc_runtime_journal "$WC_RUNTIME_INSTALL_SNAPSHOT" publish-job "$label"
  else
  sed -e "s|__RUNNER__|$RUNNER|g" -e "s|__LOG_DIR__|$LOG_DIR|g" "$template" > "$target"
  chmod 644 "$target"
  fi
  [ "$RENDER_ONLY" -eq 0 ] || continue
  label="${name%.plist}"
  "${WC_LAUNCHCTL_BIN:-launchctl}" bootout "gui/$(id -u)/$label" >/dev/null 2>&1 || true
  "${WC_LAUNCHCTL_BIN:-launchctl}" bootstrap "gui/$(id -u)" "$target"
  echo "installed $label"
done
