#!/usr/bin/env bash
# File-host installer (Windows/Linux/macOS agent). Catalog UI is ./run.sh
set -euo pipefail
cd "$(dirname "$0")/media-host"
chmod +x INSTALL.sh
exec ./INSTALL.sh
