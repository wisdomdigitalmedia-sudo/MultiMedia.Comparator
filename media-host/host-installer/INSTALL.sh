#!/usr/bin/env bash
# Media Host 1.6 — Linux/macOS click-and-run (media server).
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd .. && pwd)"

have_py() {
  command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 9))'
}

if ! have_py; then
  echo "Python 3.9+ is missing."
  if command -v apt-get >/dev/null 2>&1; then
    if [[ "$(id -u)" -eq 0 ]]; then
      apt-get update && apt-get install -y python3
    elif sudo -n true 2>/dev/null; then
      sudo -n apt-get update && sudo -n apt-get install -y python3
    else
      echo "Install Python 3, then run this again:  sudo apt install python3"
      exit 1
    fi
  else
    echo "Install Python 3.9+ and re-run."
    exit 1
  fi
fi

export PYTHONPATH="${REPO}${PYTHONPATH:+:$PYTHONPATH}"
echo "Opening Media Host setup in your browser..."
exec python3 ./wizard.py
