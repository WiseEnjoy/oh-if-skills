#!/usr/bin/env bash
# joyspace-bench-table 依赖自检（首次使用执行）。
# 脚本只用 python3 标准库，远程执行靠系统 ssh；install.sh 仅做环境自检，秒退。
set -uo pipefail
TAG="joyspace-bench-table"
MISSING=()
log()  { printf '[%s] %s\n' "$TAG" "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

log "检查依赖 ..."
have python3 || MISSING+=(python3)
have ssh     || MISSING+=(ssh)
# joycode_browser / read_joyspace 是内置工具与 MCP，不通过 command -v 检查；
# 缺失会在使用点报错，无需预装。

if [ "${#MISSING[@]}" -gt 0 ]; then
  printf '[%s] 仍缺失：%s\n' "$TAG" "${MISSING[*]}"
  exit 1
fi
python3 -I -c 'import json, glob, os, re, sys, argparse, shutil, statistics' 2>/dev/null \
  || { log "python3 标准库自检失败"; exit 1; }
log "依赖齐全（python3 标准库 + ssh）"
exit 0
