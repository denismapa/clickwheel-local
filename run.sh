#!/usr/bin/env bash
# Clickwheel: ./run.sh starts the app.
# Builds the venv on first run and installs the pinned dependencies.
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then set -a; source .env; set +a; fi

for tool in python3 ffmpeg ffprobe; do
  command -v "$tool" >/dev/null || { echo "Missing $tool. Install Homebrew packages: brew install python ffmpeg deno"; exit 1; }
done
command -v deno >/dev/null || echo "Warning: deno not found. YouTube needs a JavaScript runtime: brew install deno"

[[ -x .venv/bin/python ]] || python3 -m venv .venv
if [[ ! -f .venv/.installed || requirements.txt -nt .venv/.installed ]]; then
  .venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt
  touch .venv/.installed
fi
exec .venv/bin/python -m clickwheel "$@"
