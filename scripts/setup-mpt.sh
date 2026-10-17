#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
python3 -m venv .mpt-venv
.mpt-venv/bin/python -m pip install -r requirements-mpt.txt
printf '%s\n' 'Optional editor installed. Run n8n Setup Diagnostics, then Preflight with MoneyPrinterTurbo selected. No videos were generated.'
