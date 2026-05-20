#!/bin/sh
set -e

mkdir -p /app/data/logs

if [ ! -f /app/.env ] && [ -f /app/.env.example ]; then
    echo "[entrypoint] 未找到 .env，請掛載或建立 /app/.env（Synology 使用主機目錄的 .env）"
fi

echo "[entrypoint] 資料目錄: ${DATA_DIR:-/app/data}"
echo "[entrypoint] Web UI: http://0.0.0.0:${APP_PORT:-8000}"
echo "[entrypoint] 排程時區: ${TZ:-Asia/Taipei}"

exec python run.py
