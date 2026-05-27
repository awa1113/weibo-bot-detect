#!/usr/bin/env bash
# 微博方向社交机器人检测V1.0

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND="$ROOT/源代码/backend"
PID_FILE="$BACKEND/storage/app.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "未发现运行中的系统进程。"
  exit 0
fi

APP_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [ -z "${APP_PID:-}" ]; then
  rm -f "$PID_FILE"
  echo "PID文件为空，已清理。"
  exit 0
fi

if kill -0 "$APP_PID" >/dev/null 2>&1; then
  kill "$APP_PID"
  sleep 1
fi

rm -f "$PID_FILE"
echo "系统已停止。"
