#!/bin/sh
set -e

# === Synology NAS 權限診斷 ===
if ! touch /app/data/.permission_test 2>/dev/null; then
    echo ""
    echo "========================================================================="
    echo "   [ERROR] 資料目錄 /app/data 無寫入權限！"
    echo "   Synology NAS 部署常見的權限問題："
    echo "   請在 Synology NAS 控制台對掛載的 ./data 資料夾進行以下權限設定："
    echo "   1. 進入 DSM -> File Station -> 找到你的 data 資料夾。"
    echo "   2. 右鍵 -> 屬性 -> 權限，為 Everyone 或適當的使用者新增「讀取與寫入」權限。"
    echo "   3. 勾選「套用到此資料夾、子資料夾及檔案」並儲存。"
    echo "   - 或者在 NAS SSH 連線中執行以下指令賦予完整讀寫權限："
    echo "      sudo chmod -R 777 ./data"
    echo "========================================================================="
    echo ""
    exit 1
fi
rm -f /app/data/.permission_test

mkdir -p /app/data/logs

if [ ! -f /app/.env ] && [ -f /app/.env.example ]; then
    echo "[entrypoint] 未找到 .env，請掛載或建立 /app/.env（Synology 使用主機目錄的 .env）"
fi

echo "[entrypoint] 資料目錄: ${DATA_DIR:-/app/data}"
echo "[entrypoint] Web UI: http://0.0.0.0:${APP_PORT:-8000}"
echo "[entrypoint] 排程時區: ${TZ:-Asia/Taipei}"

exec python run.py

