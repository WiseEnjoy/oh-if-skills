#!/usr/bin/env bash
# xllm-npu-deps-bundle 依赖自检（首次使用执行）
# 幂等：依赖齐全时秒退 0；缺失则尝试安装，仍缺失就列出来并以 1 退出。
# 注意：CANN 工具链（cann-9.x、Ascend 驱动）无法由包管理器安装，需要环境自带。
set -uo pipefail
TAG="xllm-npu-deps-bundle"
MISSING=()
log()  { printf '[%s] %s\n' "$TAG" "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
pkg_mgr() {
  if have dnf; then echo dnf; elif have apt-get; then echo apt-get
  elif have yum; then echo yum; else echo ""; fi
}
install_pkg() {
  have "$2" && return 0
  local mgr; mgr="$(pkg_mgr)"
  if [ -z "$mgr" ]; then log "缺 $2：机器上没有包管理器，请手动安装 $1"; return 1; fi
  log "安装 $1 ..."
  case "$mgr" in
    dnf|yum) timeout 300 "$mgr" install -y "$1" >/dev/null 2>&1 ;;
    apt-get) timeout 300 apt-get install -y "$1" >/dev/null 2>&1 ;;
  esac
  have "$2" || { log "安装 $1 后仍未找到 $2"; return 1; }
}

log "检查依赖 ..."
install_pkg git git || MISSING+=("git (package: git)")
install_pkg python3 python3 || MISSING+=("python3 (package: python3)")
install_pkg cmake cmake || MISSING+=("cmake (package: cmake)")

# CANN 环境提示（不阻断）
if [ -z "${ASCEND_HOME_PATH:-}" ]; then
  log "提示：未检测到 ASCEND_HOME_PATH，构建前请 source CANN 环境（set_env.sh）"
fi

if [ "${#MISSING[@]}" -gt 0 ]; then
  log "以下依赖缺失，请手动安装后重试："
  printf '  - %s\n' "${MISSING[@]}"
  exit 1
fi
log "依赖齐全"
