#!/usr/bin/env bash
# xllm-build 依赖自动安装（首次使用执行）
set -uo pipefail
TAG="xllm-build"
MISSING=()
log() { printf '[%s] %s\n' "$TAG" "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
# timeout 只在 GNU coreutils 上有（macOS 没有）：有就用，没有就直接跑
run_to() { if have timeout; then timeout 300 "$@"; else "$@"; fi; }
pkg_mgr() {
  if have dnf; then echo dnf
  elif have apt-get; then echo apt-get
  elif have yum; then echo yum
  elif have apk; then echo apk
  else echo ""
  fi
}
install_pkg() {
  local pkg="$1" cmd="$2" mgr
  have "$cmd" && return 0
  mgr=$(pkg_mgr)
  if [ -z "$mgr" ]; then
    log "缺 ${cmd}：机器上没有包管理器，请手动安装 ${pkg}"
    return 1
  fi
  log "安装 $pkg ..."
  case "$mgr" in
    dnf|yum) run_to "$mgr" install -y "$pkg" >/dev/null 2>&1 ;;
    apt-get)
      run_to apt-get update -qq >/dev/null 2>&1
      run_to apt-get install -y -qq "$pkg" >/dev/null 2>&1
      ;;
    apk) run_to apk add --no-cache "$pkg" >/dev/null 2>&1 ;;
  esac
  if have "$cmd"; then
    log "已安装 $pkg"
    return 0
  fi
  log "安装失败 ${pkg}（请手动执行：${mgr} install ${pkg}）"
  return 1
}

log "检查依赖 ..."
have git || MISSING+=(git)
have python3 || MISSING+=(python3)
if [ "${#MISSING[@]}" -eq 0 ]; then
  install_pkg util-linux setsid || MISSING+=(setsid)
fi
if [ "${#MISSING[@]}" -gt 0 ]; then
  printf '[%s] 仍缺失：%s\n' "$TAG" "${MISSING[*]}"
  exit 1
fi
log "依赖齐全"
