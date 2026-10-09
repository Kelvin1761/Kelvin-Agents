#!/bin/zsh
# Invoked only by approved runtime activation. Preserve first-pass evidence.
set -eu
SKILL_DIR="${0:A:h}"
PROJECT_ROOT="${SKILL_DIR:h:h:h}"
SCRIPT_DIR="$SKILL_DIR/scripts"
LABEL="com.antigravity.central-wong-choi.research-review"
AGENTS_DIR="${WC_LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
LAUNCHCTL="${WC_LAUNCHCTL_BIN:-launchctl}"
DEST="$AGENTS_DIR/$LABEL.plist"
DOMAIN="gui/$(id -u)"
TENNIS_ROOT="${WC_TENNIS_RUNTIME_ROOT:-$HOME/Antigravity-repo/tennis-wong-choi}"
TENNIS_LOGS="${TENNIS_LOG_DIR:-$TENNIS_ROOT/data/logs}"
TZ_NAME="$(readlink /etc/localtime | sed 's#.*/zoneinfo/##')"
[ "$TZ_NAME" = "Australia/Sydney" ] || { print -u2 -- "Sydney timezone required"; exit 1; }
TEMP_DIR="$(mktemp -d -t wc-research-install)"
CHANGED=0
COMPLETE=0
WAS_LOADED=0
STAGED=""
"$LAUNCHCTL" print "$DOMAIN/$LABEL" >/dev/null 2>&1 && WAS_LOADED=1
[ ! -f "$DEST" ] || cp -p "$DEST" "$TEMP_DIR/previous.plist"
cleanup() {
  local outcome=$?
  trap - EXIT HUP INT TERM
  if [ "$COMPLETE" -ne 1 ] && [ "$CHANGED" -eq 1 ]; then
    # A concurrent writer owns its bytes. Never overwrite it during rollback.
    if ! cmp -s "$DEST" "$TEMP_DIR/candidate.plist" &&
       ! { [ -f "$TEMP_DIR/previous.plist" ] && cmp -s "$DEST" "$TEMP_DIR/previous.plist"; } &&
       ! { [ ! -e "$DEST" ] && [ ! -L "$DEST" ] && [ ! -f "$TEMP_DIR/previous.plist" ]; }; then
      print -u2 -- "CRITICAL: concurrent research plist write; rollback blocked"
      outcome=1
    else
      "$LAUNCHCTL" bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
      if [ -f "$TEMP_DIR/previous.plist" ]; then
        cp -p "$TEMP_DIR/previous.plist" "$DEST" || outcome=1
        if [ "$WAS_LOADED" -eq 1 ]; then
          "$LAUNCHCTL" bootstrap "$DOMAIN" "$DEST" || outcome=1
        fi
      else
        rm -f "$DEST" || outcome=1
      fi
    fi
  fi
  [ -z "$STAGED" ] || rm -f "$STAGED"
  # Retain snapshot on failure for manual recovery.
  if [ "$COMPLETE" -eq 1 ]; then
    rm -f "$TEMP_DIR/previous.plist" "$TEMP_DIR/candidate.plist" "$TEMP_DIR/pass.json"
    rmdir "$TEMP_DIR"
  else
    print -u2 -- "research installation failed; recovery evidence: $TEMP_DIR"
  fi
  exit "$outcome"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
export WC_PRIMARY_REPO_ROOT="$PROJECT_ROOT" WC_TENNIS_RUNTIME_ROOT="$TENNIS_ROOT" TENNIS_LOG_DIR="$TENNIS_LOGS"
# A blocked first pass remains in the append-only run log and stops activation.
/bin/zsh "$SCRIPT_DIR/run_central_research_review.sh" --initialize
/bin/zsh "$SCRIPT_DIR/run_central_research_review.sh" > "$TEMP_DIR/pass.json"
RECEIPT="$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_log"])' "$TEMP_DIR/pass.json")"
/bin/zsh "$SCRIPT_DIR/run_central_research_review.sh" --status --receipt "$RECEIPT"
# plistlib handles XML escaping in paths, including external disks with spaces.
/usr/bin/python3 - "$SKILL_DIR/launchd/$LABEL.plist.template" "$TEMP_DIR/candidate.plist" "$SCRIPT_DIR" "$PROJECT_ROOT" "$TENNIS_ROOT" "$TENNIS_LOGS" <<'PY'
import plistlib, sys
source, target, scripts, repo, tennis, logs = sys.argv[1:]
replacements = dict(zip(("__SCRIPT_DIR__", "__PROJECT_ROOT__", "__TENNIS_RUNTIME_ROOT__", "__TENNIS_LOG_DIR__"), (scripts, repo, tennis, logs)))
def render(value):
    if isinstance(value, str):
        for token, replacement in replacements.items():
            value = value.replace(token, replacement)
        return value
    if isinstance(value, list):
        return [render(item) for item in value]
    if isinstance(value, dict):
        return {key: render(item) for key, item in value.items()}
    return value
with open(source, "rb") as handle:
    payload = render(plistlib.load(handle))
with open(target, "wb") as handle:
    plistlib.dump(payload, handle)
PY
plutil -lint "$TEMP_DIR/candidate.plist"
mkdir -p "$AGENTS_DIR" "$SCRIPT_DIR/logs"
# Prepare bytes on the destination filesystem before unloading the old job.
# A failed copy never touches the installed plist; rename publishes atomically.
STAGED="$(mktemp "$AGENTS_DIR/.wc-research-install.XXXXXX")"
cp "$TEMP_DIR/candidate.plist" "$STAGED"
chmod 644 "$STAGED"
if [ -f "$TEMP_DIR/previous.plist" ]; then
  cmp -s "$DEST" "$TEMP_DIR/previous.plist" || { print -u2 -- "CRITICAL: concurrent research plist write before installation"; exit 1; }
else
  [ ! -e "$DEST" ] && [ ! -L "$DEST" ] || { print -u2 -- "CRITICAL: research plist appeared before installation"; exit 1; }
fi
# Set the recovery boundary BEFORE launchctl can unload or receive a signal.
CHANGED=1
"$LAUNCHCTL" bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
if [ -f "$TEMP_DIR/previous.plist" ]; then
  cmp -s "$DEST" "$TEMP_DIR/previous.plist" || { print -u2 -- "CRITICAL: concurrent research plist write during unload"; exit 1; }
else
  [ ! -e "$DEST" ] && [ ! -L "$DEST" ] || { print -u2 -- "CRITICAL: research plist appeared during unload"; exit 1; }
fi
mv "$STAGED" "$DEST"
STAGED=""
"$LAUNCHCTL" bootstrap "$DOMAIN" "$DEST"
"$LAUNCHCTL" enable "$DOMAIN/$LABEL"
"$LAUNCHCTL" print "$DOMAIN/$LABEL" >/dev/null
COMPLETE=1
print -r -- "research review installed: daily Sydney 07:10; acceptance $RECEIPT"
