"""
統一啟動入口
一鍵啟動：資料庫初始化 → 排程器 → FastAPI Web 伺服器
"""

import os
import sys
import io
import logging
from pathlib import Path

# === 修正 Windows 主控台 UTF-8 編碼 ===
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 確保專案目錄在 Python 路徑中
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))


def setup_logging():
    """設定日誌系統"""
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "scraper.log"

    # 使用 UTF-8 StreamHandler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.INFO)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[console_handler, file_handler],
    )

    # 減少第三方套件的日誌噪音
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def check_env():
    """檢查環境設定完整性"""
    from config import config

    print("\n" + "=" * 60)
    print("  [Scraper] Gov Procurement - Public Appeal Crawler")
    print("=" * 60)

    warnings = []

    if not config.DISCORD_WEBHOOK_URL:
        warnings.append("[!] Discord Webhook URL not configured")

    if not config.FILTER_KEYWORDS:
        warnings.append("[!] Filter keywords not configured (will scrape all)")

    if warnings:
        print("\n  Warnings:")
        for w in warnings:
            print(f"    {w}")
    else:
        print("\n  [OK] All settings are ready")

    print(f"\n  Keywords : {', '.join(config.FILTER_KEYWORDS)}")
    print(f"  Schedule : {config.SCRAPE_SCHEDULE_HOUR:02d}:{config.SCRAPE_SCHEDULE_MINUTE:02d} daily")
    print(f"  Lookback : {config.SCRAPE_LOOKBACK_DAYS} day(s)")
    print(f"  Tracking : {config.TRACK_CHECK_HOUR:02d}:{config.TRACK_CHECK_MINUTE:02d} daily")
    print(f"  Discord  : {'configured' if config.DISCORD_WEBHOOK_URL else 'not set'}")
    print(f"  Web UI   : http://{config.APP_HOST}:{config.APP_PORT}")
    print("=" * 60 + "\n")


def main():
    """主啟動流程"""
    # 1. 設定日誌
    setup_logging()
    logger = logging.getLogger(__name__)

    # 2. 檢查環境
    check_env()

    # 3. 初始化資料庫
    from models import init_db
    logger.info("Initializing database...")
    init_db()
    logger.info("Database ready")

    # 4. 啟動排程器
    from scheduler import init_scheduler
    logger.info("Starting scheduler...")
    init_scheduler()

    # 5. 啟動 Web 伺服器
    import uvicorn
    from config import config

    logger.info(f"Starting web server: http://{config.APP_HOST}:{config.APP_PORT}")

    uvicorn.run(
        "app:app",
        host=config.APP_HOST,
        port=config.APP_PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
