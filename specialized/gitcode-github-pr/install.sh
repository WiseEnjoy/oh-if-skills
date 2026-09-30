#!/usr/bin/env bash
# gitcode-github-pr 依赖自动安装（首次使用执行）
# 幂等：依赖齐全时秒退 0；缺失则尝试安装，仍缺失就列出来并以 1 退出。
set -uo pipefail
TAG="gitcode-github-pr"
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

ensure_gh() {
  have gh && return 0
  log "安装 gh CLI ..."
  local arch ver tar url
  arch=$(uname -m); case "$arch" in aarch64) arch=arm64;; x86_64) arch=amd64;; esac
  ver=$(timeout 30 env -u https_proxy -u http_proxy curl -fsSL \
        https://api.github.com/repos/cli/cli/releases/latest 2>/dev/null \
        | grep -oE '"tag_name": *"v[0-9.]+"' | grep -oE '[0-9.]+') || ver=""
  [ -z "$ver" ] && { log "取不到 gh 最新版本号"; MISSING+=("gh"); return 1; }
  tar="/tmp/gh-$ver.tar.gz"
  url="https://github.com/cli/cli/releases/download/v$ver/gh_${ver}_linux_${arch}.tar.gz"
  if ! timeout 180 env -u https_proxy -u http_proxy curl -fL --retry 3 -o "$tar" "$url"; then
    log "gh 下载失败（可手动：$url）"; MISSING+=("gh"); return 1
  fi
  mkdir -p "$HOME/.local/bin"
  tar -xzf "$tar" -C /tmp "gh_${ver}_linux_${arch}/bin/gh" 2>/dev/null \
    && mv "/tmp/gh_${ver}_linux_${arch}/bin/gh" "$HOME/.local/bin/gh" \
    && chmod +x "$HOME/.local/bin/gh" && log "已安装 gh -> ~/.local/bin/gh"
  have gh || { log "gh 装好后仍不在 PATH（需把 ~/.local/bin 加进 PATH）"; MISSING+=("gh"); }
}
log "检查依赖 ..."
need curl curl
need git git
ensure_gh

if [ "${#MISSING[@]}" -gt 0 ]; then
  printf '[%s] 仍缺失：%s\n' "$TAG" "${MISSING[*]}"
  exit 1
fi
log "依赖齐全"
exit 0
