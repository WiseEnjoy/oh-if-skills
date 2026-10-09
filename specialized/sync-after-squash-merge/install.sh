#!/usr/bin/env bash
set -euo pipefail
if command -v git >/dev/null 2>&1; then
  echo "[sync-after-squash-merge] 依赖齐全（$(git --version)）"
  exit 0
fi
echo "[sync-after-squash-merge] 缺少 git，请先安装 git" >&2
exit 1
