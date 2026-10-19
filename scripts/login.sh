#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python - <<'PY'
import fcntl
import os
import subprocess
from wondertales.store import Store
store=Store(os.environ.get('WONDERTALES_HOME','~/.local/share/wondertales-v2'))
with (store.root/'worker.lock').open('a') as lock:
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit('Stop the worker before signing into Flow.')
    raise SystemExit(subprocess.call(['.venv/bin/gflow','auth','login','--profile',store.settings()['flow_profile'],'--browser','chrome']))
PY
