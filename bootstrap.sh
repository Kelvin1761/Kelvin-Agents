#!/usr/bin/env bash
# One-shot setup for a NEW macOS/Linux machine.
# Run from the repo root after: git clone https://github.com/Kelvin1761/Kelvin-Agents.git
#
#   cd Kelvin-Agents && ./bootstrap.sh
#
# Idempotent — safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> 1/5  Python virtual environment (.venv)"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip setuptools wheel

echo "==> 2/5  Python dependencies"
pip install --quiet -r requirements.txt
if [ -f requirements-optional.txt ]; then
  pip install --quiet -r requirements-optional.txt || echo "   (optional deps skipped)"
fi

echo "==> 3/5  Playwright Chromium (for scrapers)"
python -m playwright install chromium || echo "   (playwright install skipped — run manually if you need scraping)"

echo "==> 4/5  Data location (WONGCHOI_DATA_ROOT)"
if [ -f .wongchoi_data_root ]; then
  echo "   .wongchoi_data_root already set: $(cat .wongchoi_data_root)"
else
  echo "   The big 'Wong Choi ... Analysis' data folders usually live on Google Drive,"
  echo "   separate from this code repo. Paste the path to the folder that CONTAINS them"
  echo "   (e.g. your Google Drive 'Antigravity' folder). Leave blank to use this repo dir."
  printf "   DATA_ROOT path: "
  read -r dr || dr=""
  if [ -n "$dr" ]; then
    printf '%s\n' "$dr" > .wongchoi_data_root
    echo "   wrote .wongchoi_data_root"
  else
    echo "   (left unset — DATA_ROOT defaults to this repo folder)"
  fi
fi

echo "==> 5/5  Verify resolved paths"
python3 wongchoi_paths.py

echo
echo "✅ Setup done. Each new shell: source .venv/bin/activate"
echo "   Next, read SETUP.md to run HKJC / AU / NBA / tennis Wong Choi."
