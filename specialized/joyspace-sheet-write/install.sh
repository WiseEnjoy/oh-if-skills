#!/usr/bin/env bash
# joyspace-sheet-write 依赖自检（首次使用执行）。
# 本技能无外部依赖：内置浏览器 + JoySpace MCP 即可，install.sh 仅做环境自检，秒退。
set -uo pipefail
TAG="joyspace-sheet-write"
log() { printf '[%s] %s\n' "$TAG" "$*"; }

log "检查依赖 ..."
# joycode_browser（写入）与 read_joyspace（只读校验）都是内置能力，不通过 command -v 检查；
# 缺失会在使用点报错，无需预装。本技能不调用任何外部命令。
log "依赖齐全（无外部依赖）"
exit 0
