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

# ---- tokens (optional, one-time setup) ----
# GitHub token: used by repo sources to avoid rate limits.
gh_status="absent"
if [ -n "${GITHUB_TOKEN:-}" ] || [ -n "${GH_TOKEN:-}" ]; then
  gh_status="env"
else
  if security find-generic-password -a codex -s github-token -w >/dev/null 2>&1; then
    gh_status="keychain"
  fi
fi

# GitCode token: required by the GitCode 华为生态 Issues source
# (gitcode.com/api/v5/search/issues). Without it that source times out.
gc_status="absent"
[ -n "${GITCODE_TOKEN:-}" ] && gc_status="env"
if [ "$gc_status" = "absent" ]; then
  if security find-generic-password -a codex -s gitcode-token >/dev/null 2>&1; then
    gc_status="keychain"
  fi
fi

echo
echo "tokens:"
echo "  github:  $gh_status"
echo "  gitcode: $gc_status"
if [ "$gh_status" = "absent" ]; then
  echo
  echo "  [github] 没有检测到 token。仓库类源会用匿名配额，容易触发限流。"
  echo "  获取：GitHub → Settings → Developer settings → Personal access tokens → Fine-grained，"
  echo "  勾选 public repos 的只读权限即可。"
  echo "  配置（二选一，推荐钥匙串）："
  echo "    security add-generic-password -a codex -s github-token -w '<your-token>' -U"
  echo "    export GITHUB_TOKEN=<your-token>   # 写入 ~/.zshrc 持久化"
fi
if [ "$gc_status" = "absent" ]; then
  echo
  echo "  [gitcode] 没有检测到 token。GitCode 华为生态 Issues 源将超时跳过。"
  echo "  获取：gitcode.com → 个人设置 → 私人令牌，勾选 issues 只读。"
  echo "  配置："
  echo "    export GITCODE_TOKEN=<your-token>   # 写入 ~/.zshrc 持久化"
fi
if [ "$gh_status" != "absent" ] && [ "$gc_status" != "absent" ]; then
  echo "  两个 token 都已就位，无需操作。"
fi
