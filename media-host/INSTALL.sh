#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
chmod +x host-installer/INSTALL.sh
exec ./host-installer/INSTALL.sh
