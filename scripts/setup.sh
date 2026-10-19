#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v python3 >/dev/null
command -v node >/dev/null
command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
node -e 'if(Number(process.versions.node.split(".")[0])<24)process.exit(1)'
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci
bash scripts/start.sh --doctor
printf '\nNext: bash scripts/prepare-renderer.sh, then bash scripts/login.sh\n'
