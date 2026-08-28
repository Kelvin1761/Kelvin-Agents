#!/bin/zsh
set -eu

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h:h:h}"

: "${WC_PRIMARY_REPO_ROOT:=$PROJECT_ROOT}"
: "${WONGCHOI_CONTROL_STATE_ROOT:=$HOME/WongChoiData/WongChoiControl}"
: "${WC_WARM_ARCHIVE_ROOT:=/Volumes/Kelvin Hardisk 1/WongChoi-Archive}"
export WC_PRIMARY_REPO_ROOT WONGCHOI_CONTROL_STATE_ROOT WC_WARM_ARCHIVE_ROOT

for env_file in "$HOME/.wongchoi_notify.env" "$HOME/.wongchoi_cloudflare.env"; do
  [ -f "$env_file" ] && source "$env_file"
done

if [ -z "${WC_COLD_MIRROR_ROOT:-}" ] && [ -f "$HOME/.wongchoi_cold_mirror_root" ]; then
  IFS= read -r WC_COLD_MIRROR_ROOT < "$HOME/.wongchoi_cold_mirror_root" || true
  export WC_COLD_MIRROR_ROOT
fi

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"

cd "$PROJECT_ROOT"
exec /usr/bin/python3 "$SCRIPT_DIR/central_daily_maintenance.py"
