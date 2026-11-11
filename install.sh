#!/usr/bin/env bash
# oh-if-skills 仓库安装脚本：依赖自检 → 技能契约校验 → 各 agent 软链接补链。
# 首次 clone 后、新增/删除/编辑技能后跑一次即可；幂等。
# 校验全绿才会返回 0；有契约违规时仍会完成补链，但以非 0 退出提醒修复。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

# ---------- 1. 依赖自检 ----------
MISSING=()
have() { command -v "$1" >/dev/null 2>&1; }
need() { have "$2" || MISSING+=("$2"); }
need git git
need curl curl
need python3 python3
if have python3 && ! python3 -c 'import yaml' 2>/dev/null; then
  python3 -m pip install --quiet pyyaml >/dev/null 2>&1 || true
  python3 -c 'import yaml' 2>/dev/null || MISSING+=("PyYAML (python3 -m pip install pyyaml)")
fi
if [ "${#MISSING[@]}" -gt 0 ]; then
  printf '缺依赖：%s\n' "${MISSING[*]}" >&2
  exit 1
fi

# ---------- 2. 技能契约校验（frontmatter + 四项契约） ----------
echo "== 技能契约校验 =="
VALIDATE_OK=1
python3 - <<'PYEOF' || VALIDATE_OK=0
import os, re, sys, yaml
fail = 0
for dirpath, dirnames, filenames in sorted(os.walk(".")):
    if "SKILL.md" not in filenames:
        continue
    p = os.path.join(dirpath, "SKILL.md")
    if dirpath.count(os.sep) != 2:   # 只校验 <分类>/<技能>/SKILL.md 两级布局
        continue
    t = open(p, encoding="utf-8").read()
    errs = []
    m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
    if not m:
        errs.append("NO FRONTMATTER")
        d = {}
    else:
        try:
            d = yaml.safe_load(m.group(1)) or {}
        except Exception as e:
            errs.append(f"frontmatter YAML 解析失败: {e}")
            d = {}
    name = d.get("name")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name or "", ) or len(name or "") > 64:
        errs.append(f"bad name: {name!r}")
    if name != os.path.basename(dirpath):
        errs.append(f"name != dir basename: {name!r} vs {os.path.basename(dirpath)}")
    desc = d.get("description")
    if not isinstance(desc, str) or not desc or len(desc) > 1024:
        errs.append(f"bad description (type={type(desc).__name__}, len={len(desc) if isinstance(desc,str) else 'n/a'})")
    if "## 依赖（首次使用自动安装）" not in t:
        errs.append("missing dependency section")
    if not os.path.isfile(os.path.join(dirpath, "install.sh")):
        errs.append("missing install.sh")
    if name != "user-communication" and "## 输出范式（所有技能统一）" not in t:
        errs.append("missing output-paradigm block")
    if errs:
        fail += 1
        print(f"  FAIL {p}")
        for e in errs:
            print(f"       - {e}")
    else:
        print(f"  OK   {p}  (desc_len={len(desc)})")
sys.exit(1 if fail else 0)
PYEOF
if [ "$VALIDATE_OK" -ne 1 ]; then
  echo "!! 契约校验未全绿；链接仍会更新，修复后再提交。" >&2
fi

# ---------- 3. 各 agent 软链接补链 ----------
echo "== 补链 =="
CATS="meta specialized"
CHANGED=0
note() { printf '  %s\n' "$*"; CHANGED=$((CHANGED+1)); }

link() {                   # $1 = 链接路径, $2 = 指向
  [ -L "$1" ] && [ "$(readlink "$1")" = "$2" ] && return 0
  if [ -e "$1" ] && [ ! -L "$1" ]; then
    note "跳过 $(basename "$1")：已存在同名真实目录（非本仓），不覆盖"
    return 0
  fi
  ln -sfn "$2" "$1" && note "+ $(basename "$1") -> $2"
}

prune_dangling() {         # $1 = 目录, $2 = 子路径模式（可为空）
  for l in "$1"/*; do
    [ -L "$l" ] || continue
    case "$(readlink "$l")" in
      "$REPO"/*) [ -e "$l" ] || { rm -f "$l"; note "- 清理失效链接：$(basename "$l")"; };;
    esac
  done
}

link_categories() {        # $1 = 目标技能目录（分类级软链接）
  [ -d "$1" ] || return 0
  echo "分类级：$1"
  for c in $CATS; do link "$1/$c" "$REPO/$c"; done
  prune_dangling "$1"
}

link_flat() {              # $1 = 目标技能目录（逐技能软链接）
  [ -d "$1" ] || return 0
  echo "逐技能：$1"
  for d in "$REPO"/{meta,specialized}/*/; do
    [ -f "$d/SKILL.md" ] || continue
    link "$1/$(basename "$d")" "${d%/}"
  done
  prune_dangling "$1"
}

seen=""
for home in "${CODEX_HOME:-$HOME/.codex}/skills" "$HOME/.joycode/skills" "$HOME/.config/opencode/skills"; do
  case " $seen " in *" $home "*) continue;; esac
  seen="$seen $home"
  link_categories "$home"
done
link_flat "$HOME/.claude/skills"

if [ "$CHANGED" -eq 0 ]; then echo "链接全部已是最新，无改动。"; else echo "补链完成，$CHANGED 处改动；各 agent 下一轮会话生效。"; fi
[ "$VALIDATE_OK" -eq 1 ] || exit 1
exit 0
