#!/usr/bin/env bash
# 微博方向社交机器人检测V1.0

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND="$ROOT/源代码/backend"
PORT=18081
PID_FILE="$BACKEND/storage/app.pid"
OUT_LOG="$BACKEND/storage/backend_stdout.log"
ERR_LOG="$BACKEND/storage/backend_stderr.log"

mkdir -p "$BACKEND/storage"

if [ ! -x "$BACKEND/.venv/bin/python" ]; then
  echo "未找到Python虚拟环境，请先运行 deploy.sh。"
  exit 1
fi

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" >/dev/null 2>&1; then
    echo "系统已经在运行，PID=$OLD_PID"
    echo "本机访问: http://127.0.0.1:$PORT"
    exit 0
  fi
fi

python3 - "$PORT" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket() as sock:
    sock.settimeout(0.5)
    result = sock.connect_ex(("127.0.0.1", port))
    if result == 0:
        raise SystemExit("端口已被占用，请先释放18081端口后重试。")
PY

cd "$BACKEND"
nohup "$BACKEND/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" >"$OUT_LOG" 2>"$ERR_LOG" &
APP_PID=$!
echo "$APP_PID" > "$PID_FILE"

for _ in $(seq 1 30); do
  if python3 - "$PORT" <<'PY'
import sys
from urllib.request import urlopen

port = int(sys.argv[1])
try:
    with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
  then
    LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    echo "系统启动成功。"
    echo "本机访问: http://127.0.0.1:$PORT"
    if [ -n "${LAN_IP:-}" ]; then
      echo "局域网访问: http://$LAN_IP:$PORT"
    fi
    echo "日志文件: $OUT_LOG"
    exit 0
  fi
  sleep 1
done

echo "系统启动超时，请查看日志:"
echo "$OUT_LOG"
echo "$ERR_LOG"
exit 1
