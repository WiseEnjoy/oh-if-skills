#!/usr/bin/env bash
# joyspace-sheet-image 依赖自检（首次使用执行）。
# 本技能无外部依赖：内置浏览器 + 系统 ssh 即可，install.sh 仅做环境自检，秒退。
set -uo pipefail
TAG="joyspace-sheet-image"
MISSING=()
log()  { printf '[%s] %s\n' "$TAG" "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

log "检查依赖 ..."
have ssh   || MISSING+=(ssh)
# joycode_browser 是内置工具，不通过 command -v 检查；缺失会在使用点报错，无需预装。

if [ "${#MISSING[@]}" -gt 0 ]; then
  printf '[%s] 仍缺失：%s\n' "$TAG" "${MISSING[*]}"
  exit 1
fi
log "依赖齐全（无外部依赖）"
exit 0
