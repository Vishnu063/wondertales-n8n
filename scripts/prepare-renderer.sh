#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.venv/bin:$PWD/node_modules/.bin:$PATH"
.venv/bin/python - <<'PY'
import os
from pathlib import Path
from wondertales.store import Store
from wondertales.media import author_project, command, local_hypit
store=Store(os.environ.get('WONDERTALES_HOME','~/.local/share/wondertales-v2'))
work=store.root/'hypit'
work.mkdir(exist_ok=True)
author_project(work, {'title':'Local renderer setup','story':'','language':'English','style':'','duration':8,'aspect':'9:16','scenes':[]}, store.settings()['chrome_path'])
command([local_hypit(),'programs','prepare','--endpoint','html.local','--project',work,'--runtime',work/'hypit.runtime.json'],timeout=1800)
(work/'prepared').write_text(store.settings()['chrome_path'])
print('Local Hypit renderer prepared. No Google generation was requested.')
PY
