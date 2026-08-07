#!/usr/bin/env bash
set -euo pipefail
mkdir -p /data/catalogs /data/rendered
exec python -m app.main
