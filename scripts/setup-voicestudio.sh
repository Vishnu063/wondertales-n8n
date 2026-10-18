#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
command -v git >/dev/null || { printf '%s\n' 'Install git first.' >&2; exit 1; }
command -v uv >/dev/null || { printf '%s\n' 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' >&2; exit 1; }
voice_revision=4e61c2782d51df5488b390699d2faa98be677090
if [[ ! -d .voicestudio ]]; then
  git clone --filter=blob:none --no-checkout https://github.com/Vishnu063/VoiceStudio.git .voicestudio
  git -C .voicestudio checkout --detach "$voice_revision"
fi
[[ "$(git -C .voicestudio rev-parse HEAD)" == "$voice_revision" ]] || { printf '%s\n' 'Existing VoiceStudio checkout differs from the inspected revision. Preserve your changes and review the integration before updating it.' >&2; exit 1; }
cd .voicestudio
uv sync --locked --no-dev --python 3.12
printf '%s\n' 'VoiceStudio dependencies installed separately. Model downloads and a real audio sample still need validation. Start it with bash scripts/start-voicestudio.sh from the WonderTales checkout.'
