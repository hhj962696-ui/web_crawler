"""
組態管理模組
讀取 .env 檔案並提供全域設定
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 載入 .env 檔案
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    """全域設定"""

    # 基本路徑
    BASE_DIR = BASE_DIR
    DB_PATH = BASE_DIR / "database.db"
    LOG_DIR = BASE_DIR / "logs"
    LOG_FILE = LOG_DIR / "scraper.log"

    # Discord
    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

    # 排程設定
    SCRAPE_SCHEDULE_HOUR = int(os.getenv("SCRAPE_SCHEDULE_HOUR", "8"))
    SCRAPE_SCHEDULE_MINUTE = int(os.getenv("SCRAPE_SCHEDULE_MINUTE", "10"))
    TRACK_CHECK_HOUR = int(os.getenv("TRACK_CHECK_HOUR", "12"))
    TRACK_CHECK_MINUTE = int(os.getenv("TRACK_CHECK_MINUTE", "0"))

    # 篩選關鍵字
    FILTER_KEYWORDS = [
        kw.strip()
        for kw in os.getenv(
            "FILTER_KEYWORDS",
            "網路設備,資訊設備,通訊設備,路由器,交換器"
        ).split(",")
        if kw.strip()
    ]

    # Chrome
    CHROME_HEADLESS = os.getenv("CHROME_HEADLESS", "true").lower() == "true"

    # 應用
    APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
    APP_PORT = int(os.getenv("APP_PORT", "8000"))

    # 爬蟲設定
    PCC_BASE_URL = "https://web.pcc.gov.tw"
    PCC_SEARCH_URL = f"{PCC_BASE_URL}/prkms/tpAppeal/common/readTpAppeal"
    PCC_INDEX_URL = f"{PCC_BASE_URL}/prkms/tpAppeal/common/indexTpAppeal"
    REQUEST_DELAY_MIN = 2  # 最小延遲秒數
    REQUEST_DELAY_MAX = 5  # 最大延遲秒數
    MAX_RETRIES = 3  # 最大重試次數

    # 資料庫
    DATABASE_URL = f"sqlite:///{DB_PATH}"

    @classmethod
    def reload(cls):
        """重新載入環境變數"""
        load_dotenv(cls.BASE_DIR / ".env", override=True)
        cls.DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
        cls.SCRAPE_SCHEDULE_HOUR = int(os.getenv("SCRAPE_SCHEDULE_HOUR", "8"))
        cls.SCRAPE_SCHEDULE_MINUTE = int(os.getenv("SCRAPE_SCHEDULE_MINUTE", "10"))
        cls.TRACK_CHECK_HOUR = int(os.getenv("TRACK_CHECK_HOUR", "12"))
        cls.TRACK_CHECK_MINUTE = int(os.getenv("TRACK_CHECK_MINUTE", "0"))
        cls.FILTER_KEYWORDS = [
            kw.strip()
            for kw in os.getenv(
                "FILTER_KEYWORDS",
                "網路設備,資訊設備,通訊設備,路由器,交換器"
            ).split(",")
            if kw.strip()
        ]
        cls.CHROME_HEADLESS = os.getenv("CHROME_HEADLESS", "true").lower() == "true"


config = Config()
