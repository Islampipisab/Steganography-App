#!/usr/bin/env bash
# Run ON THE LINUX SERVER from stego_project root, after new code is in place:
#   cd ~/stego_project && bash deploy/server-restart.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source venv/bin/activate
pip install -r requirements.txt
systemctl restart stego-web
systemctl status stego-web --no-pager
