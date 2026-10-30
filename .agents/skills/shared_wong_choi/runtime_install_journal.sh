# Shared by the approved native installer entrypoints; sourcing only defines a function.
wc_runtime_journal() {
  local _wc_snapshot="$1" _wc_mode="$2" _wc_label="${3:-}" _wc_commit="${4:-}"
  local _wc_repo="${CUTOVER_REPO:-${PROJECT_ROOT:?}}"
  local -a _wc_journal_args
  _wc_journal_args=(--mode "$_wc_mode" --snapshot "$_wc_snapshot"
    --agents "${WC_LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
    --launchctl "${WC_LAUNCHCTL_BIN:-launchctl}" --domain "gui/$(id -u)")
  _wc_journal_args+=(--repo "$_wc_repo")
  [ -z "${WC_RUNTIME_EXPECTED_COMMIT:-}" ] || _wc_journal_args+=(--expected-commit "$WC_RUNTIME_EXPECTED_COMMIT")
  [ -z "$_wc_label" ] || _wc_journal_args+=(--label "$_wc_label")
  [ -z "$_wc_commit" ] || _wc_journal_args+=(--commit "$_wc_commit")
  /usr/bin/python3 "$_wc_repo/.agents/skills/shared_wong_choi/runtime_install_journal.py" "${_wc_journal_args[@]}"
}
