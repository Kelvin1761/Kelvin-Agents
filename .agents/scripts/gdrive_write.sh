#!/bin/bash
# gdrive_write.sh — One-line wrapper for safe_file_writer.py (WLTM mode)
#
# Usage:
#   echo "content" | bash gdrive_write.sh /target/path.md [overwrite|append|create]
#   cat source.md  | bash gdrive_write.sh /target/path.md
#
# Arguments:
#   $1 = target file path (required)
#   $2 = mode: overwrite (default), append, create
#
set -euo pipefail

TARGET="${1:?Error: target file path is required as first argument}"
MODE="${2:-overwrite}"

# Resolve script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SAFE_WRITER="${SCRIPT_DIR}/safe_file_writer.py"

if [ ! -f "$SAFE_WRITER" ]; then
    echo '{"success": false, "message": "Error: safe_file_writer.py not found at '"$SAFE_WRITER"'"}'
    exit 1
fi

# Read content from stdin, base64 encode, and pass to safe_file_writer
CONTENT="$(cat)"
B64="$(echo -n "$CONTENT" | base64)"

python "$SAFE_WRITER" --target "$TARGET" --mode "$MODE" --content "$B64"
