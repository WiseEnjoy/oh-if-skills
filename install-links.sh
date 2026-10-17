#!/usr/bin/env bash
# 把本仓库的技能链接进本机各 agent 的技能目录（幂等，可反复跑）。
# Codex/JoyCode 实测支持嵌套发现 -> 用分类软链接，新增技能零维护。
# Claude Code 按文档只认一级 <name>/SKILL.md -> 用逐技能软链接，本脚本负责补齐与清理失效链接。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CATS="meta common specialized"

link_categories() {        # $1 = 目标技能目录
  [ -d "$1" ] || return 0
  for c in $CATS; do ln -sfn "$REPO/$c" "$1/$c"; done
  echo "  [分类软链接] $1 <- $CATS"
}
link_flat() {              # $1 = 目标技能目录
  [ -d "$1" ] || return 0
  local n=0
  for d in "$REPO"/{meta,common,specialized}/*/; do
    [ -f "$d/SKILL.md" ] || continue
    ln -sfn "${d%/}" "$1/$(basename "$d")"; n=$((n+1))
  done
  # 清理指向本仓库但已消失的技能
  for l in "$1"/*; do
    [ -L "$l" ] || continue
    case "$(readlink "$l")" in "$REPO"/*) [ -e "$l" ] || { rm -f "$l"; echo "  [清理失效] $l"; };; esac
  done
  echo "  [逐技能软链接] $1 <- $n 个技能"
}

seen=""
for home in "${CODEX_HOME:-$HOME/.codex}/skills" "$HOME/.joycode/skills" "$HOME/.config/opencode/skills"; do
  case " $seen " in *" $home "*) continue;; esac   # CODEX_HOME 可能就指向 .joycode，去重
  seen="$seen $home"
  link_categories "$home"
done
link_flat "$HOME/.claude/skills"
echo "完成。各 agent 下一轮会话生效。"
