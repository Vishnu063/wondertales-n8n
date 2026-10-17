#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python - "${1:-wondertales}" <<'PY'
import fcntl
import os
from pathlib import Path
import re
import subprocess
import sys
profile = sys.argv[1]
if not re.fullmatch(r'[A-Za-z0-9_-]+', profile):
    raise SystemExit('Use a profile name with letters, numbers, underscores, or hyphens.')
root = Path(os.environ.get('WONDERTALES_HOME', '~/.local/share/wondertales')).expanduser()
root.mkdir(parents=True, exist_ok=True, mode=0o700)
with (root/'worker.lock').open('a') as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Stop the local worker before signing in, then restart it after login.')
    raise SystemExit(subprocess.call(['.venv/bin/gflow','auth','login','--profile',profile,'--browser','chrome']))
PY
