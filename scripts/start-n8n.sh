#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
export N8N_LISTEN_ADDRESS=127.0.0.1
export N8N_USER_FOLDER="${WONDERTALES_HOME:-$HOME/.local/share/wondertales}/n8n"
export N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true
mkdir -p "$N8N_USER_FOLDER"
if [[ ! -x .runtime/node_modules/.bin/n8n ]]; then
  printf '%s\n' 'Run bash scripts/setup.sh first.' >&2
  exit 1
fi
exec .runtime/node_modules/.bin/n8n start
