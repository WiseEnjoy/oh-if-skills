#!/usr/bin/env bash
# sync-links.sh —— 把本仓技能幂等挂到本机各 agent 的技能目录；可反复跑，无副作用。
#
# 为什么不能三个 agent 统一用分类级软链接（2026-11-11 实测，别再试了）：
#   Claude Code 只发现 ~/.claude/skills 下【一级】目录里的 SKILL.md。
#   实测方法：平铺探针 ~/.claude/skills/zzprobe-flat/SKILL.md 立即出现在技能列表；
#             嵌套探针 ~/.claude/skills/zzprobecat/zzprobe-nested/SKILL.md 始终不出现。
#   结论：Claude Code 侧必须【逐技能】软链接，新技能进仓不会自动可见——靠本脚本补齐，
#         而不是靠人记得手工 ln -s。
#   opencode / joycode 侧递归发现嵌套 SKILL.md，分类级软链接即可，一次挂好永不用补。
#   codex 侧已挂分类级软链接，其递归发现能力待实测（见 SKILL.md 第四节）。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CATS=(common meta specialized)
CHANGED=0
log()  { printf '%s\n' "$*"; }
note() { printf '  %s\n' "$*"; CHANGED=$((CHANGED+1)); }

# ---------- 1. 分类级软链接：opencode / joycode / codex ----------
for base in "$HOME/.config/opencode/skills" "$HOME/.joycode/skills" "$HOME/.codex/skills"; do
  [ -d "$base" ] || { log "跳过（目录不存在）：$base"; continue; }
  log "分类级：$base"
  for c in "${CATS[@]}"; do
    want="$REPO/$c"; link="$base/$c"
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$want" ]; then continue; fi
    if [ -e "$link" ] && [ ! -L "$link" ]; then
      note "！$c 是真实目录不是软链接，人工确认后再处理，本脚本不动它"
      continue
    fi
    ln -sfn "$want" "$link" && note "+ $c -> $want"
  done
done

# ---------- 2. 逐技能软链接：Claude Code ----------
CC="$HOME/.claude/skills"
if [ -d "$CC" ]; then
  log "逐技能：$CC"
  for c in "${CATS[@]}"; do
    for d in "$REPO/$c"/*/; do
      [ -f "$d/SKILL.md" ] || continue
      n="$(basename "$d")"; want="${d%/}"; link="$CC/$n"
      if [ -L "$link" ] && [ "$(readlink "$link")" = "$want" ]; then continue; fi
      if [ -e "$link" ] && [ ! -L "$link" ]; then
        note "！$n 在 Claude Code 下是真实目录（非本仓技能），跳过不覆盖"
        continue
      fi
      ln -sfn "$want" "$link" && note "+ $n -> $want"
    done
  done
  # 清理指向本仓但已失效的旧链接（技能改名/删除后的悬空链接）；只删软链接，不碰真实目录
  for link in "$CC"/*; do
    [ -L "$link" ] || continue
    tgt="$(readlink "$link")"
    case "$tgt" in "$REPO"/*) ;; *) continue;; esac
    [ -f "$link/SKILL.md" ] || { rm "$link" && note "- 悬空链接已删：$(basename "$link") -> $tgt"; }
  done
else
  log "跳过（目录不存在）：$CC"
fi

if [ "$CHANGED" -eq 0 ]; then log "全部已是最新，无改动。"; else log "完成，$CHANGED 处改动。"; fi
exit 0
