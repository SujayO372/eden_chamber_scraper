#!/usr/bin/env bash
set -euo pipefail
source .venv/bin/activate
python -m scraper.main --config config.ini
