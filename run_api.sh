#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec python3 -m manim_api --host 0.0.0.0 --port "${1:-18610}"
