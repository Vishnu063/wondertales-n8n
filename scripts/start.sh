#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
export PATH="$PWD/.venv/bin:$PATH"
exec python -m wondertales.app "$@"
