#!/usr/bin/env bash
# opencode-skills-sync 依赖自动安装（首次使用执行）
# 幂等：依赖齐全时秒退 0；缺失则尝试安装，仍缺失就列出来并以 1 退出。
set -uo pipefail
TAG="opencode-skills-sync"
MISSING=()
log()  { printf '[%s] %s\n' "$TAG" "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
pkg_mgr() {
  if have dnf; then echo dnf; elif have apt-get; then echo apt-get;
  elif have yum; then echo yum; elif have apk; then echo apk; else echo ""; fi
}
install_pkg() {          # $1=包名 $2=安装后应提供的命令
  have "$2" && return 0
  local mgr; mgr=$(pkg_mgr)
  if [ -z "$mgr" ]; then log "缺 $2：机器上没有包管理器，请手动安装 $1"; return 1; fi
  log "安装 $1 ..."
  case "$mgr" in
    dnf|yum)   timeout 300 "$mgr" install -y "$1" >/dev/null 2>&1 ;;
    apt-get)   timeout 300 apt-get update -qq >/dev/null 2>&1
               timeout 300 apt-get install -y -qq "$1" >/dev/null 2>&1 ;;
    apk)       timeout 300 apk add --no-cache "$1" >/dev/null 2>&1 ;;
  esac
  if have "$2"; then log "已安装 $1"; return 0; fi
  log "安装失败 $1（请手动执行：$mgr install $1）"; return 1
}
need() {                  # $1=包名 $2=命令
  have "$2" && return 0
  install_pkg "$1" "$2" || MISSING+=("$2")
}

ensure_pyyaml() {
  have python3 || { MISSING+=("python3"); return 1; }
  if python3 -c 'import yaml' 2>/dev/null; then return 0; fi
  log "安装 PyYAML ..."
  python3 -m pip install --quiet pyyaml >/dev/null 2>&1 || true
  if python3 -c 'import yaml' 2>/dev/null; then log "已安装 PyYAML"; return 0; fi
  install_pkg python3-pyyaml python3 >/dev/null 2>&1 || true
  python3 -c 'import yaml' 2>/dev/null && { log "已安装 PyYAML"; return 0; }
  log "PyYAML 安装失败（请手动：python3 -m pip install pyyaml）"
  MISSING+=("PyYAML")
}
log "检查依赖 ..."
need git git
need curl curl
ensure_pyyaml

if [ "${#MISSING[@]}" -gt 0 ]; then
  printf '[%s] 仍缺失：%s\n' "$TAG" "${MISSING[*]}"
  exit 1
fi
log "依赖齐全"
exit 0
