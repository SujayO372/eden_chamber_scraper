#!/usr/bin/env bash
set -euo pipefail
source .venv/bin/activate
python -m playwright install
echo "✅ Playwright browsers installed."
