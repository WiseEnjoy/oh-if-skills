#!/usr/bin/env bash
set -euo pipefail

missing=0
for cmd in python3 curl git; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "missing dependency: $cmd" >&2
    missing=1
  fi
done

if [ "$missing" -ne 0 ]; then
  exit 1
fi

python3 - <<'PY'
import sys

if sys.version_info < (3, 10):
    raise SystemExit(f"python3 >= 3.10 required, found {sys.version.split()[0]}")
print("daily: dependencies ready")
PY
