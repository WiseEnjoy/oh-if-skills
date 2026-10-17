#!/usr/bin/env bash
# pr-mr-workflow 依赖自检（首次使用执行）
# 幂等：依赖齐全时秒退 0；缺失则列出来并以 1 退出。
set -uo pipefail
TAG="pr-mr-workflow"
have() { command -v "$1" >/dev/null 2>&1; }
if have git; then
  printf '[%s] 依赖齐全\n' "$TAG"; exit 0
fi
printf '[%s] 仍缺失：git（请用系统包管理器安装）\n' "$TAG"; exit 1
