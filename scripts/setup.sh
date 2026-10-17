#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
command -v python3 >/dev/null || { printf '%s\n' 'Install Python 3.11+ first.' >&2; exit 1; }
command -v npm >/dev/null || { printf '%s\n' 'Install an n8n-supported Node.js version first (see README).' >&2; exit 1; }
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/playwright install chromium
# npm records the resolved version locally; never installs globally or needs sudo.
npm install --prefix .runtime --save-exact n8n
.venv/bin/python -m wondertales.app --doctor || true
printf '%s\n' 'Setup complete. Install missing Chrome/FFmpeg/fonts if reported; sign in with scripts/login.sh before starting the worker.'
