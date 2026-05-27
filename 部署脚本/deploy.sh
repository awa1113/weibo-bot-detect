#!/usr/bin/env bash
# 微博方向社交机器人检测V1.0

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND="$ROOT/源代码/backend"
FRONTEND="$ROOT/源代码/frontend"
PORT=18081
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

step() {
  echo
  echo "==> $1"
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

pkg_install() {
  local packages=("$@")
  if have_cmd apt-get; then
    local prefix=""
    if [ "$(id -u)" -ne 0 ]; then
      if have_cmd sudo; then
        prefix="sudo"
      else
        echo "缺少系统依赖: ${packages[*]}，并且当前环境没有sudo权限。"
        exit 1
      fi
    fi
    $prefix apt-get update
    $prefix apt-get install -y "${packages[@]}"
    return
  fi
  if have_cmd dnf; then
    local prefix=""
    if [ "$(id -u)" -ne 0 ]; then
      if have_cmd sudo; then
        prefix="sudo"
      else
        echo "缺少系统依赖: ${packages[*]}，并且当前环境没有sudo权限。"
        exit 1
      fi
    fi
    $prefix dnf install -y "${packages[@]}"
    return
  fi
  if have_cmd yum; then
    local prefix=""
    if [ "$(id -u)" -ne 0 ]; then
      if have_cmd sudo; then
        prefix="sudo"
      else
        echo "缺少系统依赖: ${packages[*]}，并且当前环境没有sudo权限。"
        exit 1
      fi
    fi
    $prefix yum install -y "${packages[@]}"
    return
  fi
  echo "未识别的Linux包管理器，请先手动安装: ${packages[*]}"
  exit 1
}

ensure_python() {
  if have_cmd python3; then
    PYTHON_BIN="python3"
    return
  fi
  step "未检测到python3，尝试自动安装"
  pkg_install python3 python3-venv python3-pip
  if ! have_cmd python3; then
    echo "python3安装失败，请手动安装后重试。"
    exit 1
  fi
  PYTHON_BIN="python3"
}

ensure_node() {
  if have_cmd node && have_cmd npm; then
    return
  fi
  step "未检测到Node.js或npm，尝试自动安装"
  pkg_install nodejs npm
  if ! have_cmd node || ! have_cmd npm; then
    echo "Node.js或npm安装失败，请手动安装LTS版本后重试。"
    exit 1
  fi
}

port_in_use() {
  "$PYTHON_BIN" - "$PORT" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket() as sock:
    sock.settimeout(0.5)
    result = sock.connect_ex(("127.0.0.1", port))
    sys.exit(0 if result == 0 else 1)
PY
}

step "检查运行环境"
ensure_python
ensure_node

if [ ! -d "$BACKEND/.venv" ]; then
  step "创建Python虚拟环境"
  "$PYTHON_BIN" -m venv "$BACKEND/.venv"
else
  step "复用现有Python虚拟环境"
fi

source "$BACKEND/.venv/bin/activate"

step "安装或校验后端依赖"
python -m pip install --upgrade pip -i "$PIP_INDEX_URL"
python -m pip install -r "$BACKEND/requirements.txt" -i "$PIP_INDEX_URL"
python -m playwright install chromium

step "安装或校验前端依赖"
cd "$FRONTEND"
npm install

step "构建前端页面"
npm run build

if [ ! -f "$BACKEND/.env" ]; then
  step "生成默认环境配置"
  cp "$BACKEND/.env.example" "$BACKEND/.env"
fi

step "启动系统"
"$SCRIPT_DIR/start.sh"

echo
echo "部署完成。"
echo "本机访问: http://127.0.0.1:$PORT"
echo "局域网或NAT访问: http://<服务器IP>:$PORT"
