#!/bin/bash
set -euo pipefail
project_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$project_root"
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo 'LocalTranscribe requires an Apple Silicon Mac.'
  exit 1
fi
IFS='.' read -r os_major os_minor os_patch <<< "$(sw_vers -productVersion)"
if [[ "$os_major" -lt 26 || ( "$os_major" -eq 26 && "${os_minor:-0}" -lt 2 ) ]]; then
  echo 'The pinned MLX runtime requires macOS 26.2 or later.'
  exit 1
fi
for tool in uv ffmpeg ffprobe xcrun; do
  if ! command -v "$tool" >/dev/null; then
    echo "Missing prerequisite: $tool. See README.md for setup instructions."
    exit 1
  fi
done
if [[ ! -x .venv/bin/python ]]; then
  uv venv --python 3.10 .venv
fi
uv pip install --python .venv/bin/python -r requirements.lock
if [[ ! -f models/whisper-turbo/weights.safetensors && ! -f models/whisper-turbo/weights.npz ]]; then
  HF_HOME="$project_root/hf-cache" HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 \
    .venv/bin/python prepare_model.py models/whisper-turbo --revision a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb
fi
.venv/bin/python scripts/build_app.py
echo 'Ready. Open LocalTranscribe.app in this folder and select the recordings you want.'
