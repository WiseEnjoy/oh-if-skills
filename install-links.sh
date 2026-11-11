#!/usr/bin/env bash
# 把本仓库的技能链接进本机各 agent 的技能目录。幂等，可反复跑；新增或删除技能后跑一次。
#
# 挂法按 agent 的发现能力分两种（实测结论，别统一）：
#   Codex / JoyCode / OpenCode  递归发现嵌套 SKILL.md -> 分类级软链接，新增技能零维护
#   Claude Code                 只发现一级目录 <name>/SKILL.md -> 逐技能软链接，必须补齐
#     （2026-11-11 实测：平铺探针 ~/.claude/skills/<name>/SKILL.md 立即出现在技能列表；
#       嵌套探针 ~/.claude/skills/<分类>/<name>/SKILL.md 始终不出现）
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CATS="meta common specialized"
CHANGED=0
note() { printf '  %s\n' "$*"; CHANGED=$((CHANGED+1)); }   # 真实改动，计数
warn() { printf '  %s\n' "$*"; }                             # 仅提示，不计改动

# 建一个软链接；已正确就跳过，目标是真实目录（别处装的同名技能）就跳过不覆盖
link() {                   # $1 = 链接路径, $2 = 指向
  [ -L "$1" ] && [ "$(readlink "$1")" = "$2" ] && return 0
  if [ -e "$1" ] && [ ! -L "$1" ]; then
    warn "跳过 $(basename "$1")：已存在同名真实目录（非本仓技能），不覆盖"
    return 0
  fi
  ln -sfn "$2" "$1" && note "+ $(basename "$1") -> $2"
}

link_categories() {        # $1 = 目标技能目录
  [ -d "$1" ] || return 0
  echo "分类级：$1"
  for c in $CATS; do link "$1/$c" "$REPO/$c"; done
}

link_flat() {              # $1 = 目标技能目录
  [ -d "$1" ] || return 0
  echo "逐技能：$1"
  for d in "$REPO"/{meta,common,specialized}/*/; do
    [ -f "$d/SKILL.md" ] || continue
    link "$1/$(basename "$d")" "${d%/}"
  done
  # 清理指向本仓库但已失效的链接（技能改名或删除后的残留）；只删软链接，不碰真实目录
  for l in "$1"/*; do
    [ -L "$l" ] || continue
    case "$(readlink "$l")" in
      "$REPO"/*) [ -f "$l/SKILL.md" ] || { rm -f "$l"; note "- 清理失效链接：$(basename "$l")"; };;
    esac
  done
}

seen=""
for home in "${CODEX_HOME:-$HOME/.codex}/skills" "$HOME/.joycode/skills" "$HOME/.config/opencode/skills"; do
  case " $seen " in *" $home "*) continue;; esac   # CODEX_HOME 可能就指向 .joycode，去重
  seen="$seen $home"
  link_categories "$home"
done
link_flat "$HOME/.claude/skills"

if [ "$CHANGED" -eq 0 ]; then echo "全部已是最新，无改动。"; else echo "完成，$CHANGED 处改动；各 agent 下一轮会话生效。"; fi
exit 0
