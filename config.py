"""
組態管理模組
讀取 .env 檔案並提供全域設定
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 載入 .env 檔案（Windows 須指定 UTF-8，否則中文關鍵字會亂碼）
BASE_DIR = Path(__file__).resolve().parent
_ENV_PATH = BASE_DIR / ".env"
load_dotenv(_ENV_PATH, encoding="utf-8")


class Config:
    """全域設定"""

    # 專案根目錄（與模組層級 BASE_DIR 相同，供 app 寫入 .env 等）
    BASE_DIR = BASE_DIR

    # 基本路徑（Docker 可設 DATA_DIR=/app/data 持久化資料庫與日誌）
    DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR)))
    DB_PATH = DATA_DIR / "database.db"
    LOG_DIR = DATA_DIR / "logs"
    LOG_FILE = LOG_DIR / "scraper.log"

    # Discord
    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
    BIDDING_DISCORD_WEBHOOK_URL = os.getenv("BIDDING_DISCORD_WEBHOOK_URL", "")
    SALES_DISCORD_WEBHOOK_URL = os.getenv("SALES_DISCORD_WEBHOOK_URL", "")

    # 排程設定
    SCRAPE_SCHEDULE_HOUR = int(os.getenv("SCRAPE_SCHEDULE_HOUR", "8"))
    SCRAPE_SCHEDULE_MINUTE = int(os.getenv("SCRAPE_SCHEDULE_MINUTE", "10"))
    BIDDING_SCHEDULE_HOUR = int(os.getenv("BIDDING_SCHEDULE_HOUR", "9"))
    BIDDING_SCHEDULE_MINUTE = int(os.getenv("BIDDING_SCHEDULE_MINUTE", "0"))
    TRACK_CHECK_HOUR = int(os.getenv("TRACK_CHECK_HOUR", "12"))
    TRACK_CHECK_MINUTE = int(os.getenv("TRACK_CHECK_MINUTE", "0"))
    HEALTH_CHECK_HOUR = int(os.getenv("HEALTH_CHECK_HOUR", "8"))
    HEALTH_CHECK_MINUTE = int(os.getenv("HEALTH_CHECK_MINUTE", "0"))
    JOB104_SCHEDULE_HOUR = int(os.getenv("JOB104_SCHEDULE_HOUR", "10"))
    JOB104_SCHEDULE_MINUTE = int(os.getenv("JOB104_SCHEDULE_MINUTE", "0"))
    SALES_SUMMARY_HOUR = int(os.getenv("SALES_SUMMARY_HOUR", "17"))
    SALES_SUMMARY_MINUTE = int(os.getenv("SALES_SUMMARY_MINUTE", "0"))

    # 104 探測器 — 略過的機關名稱關鍵字
    JOB104_SKIP_KEYWORDS = [
        kw.strip()
        for kw in os.getenv(
            "JOB104_SKIP_KEYWORDS",
            "大學,學院,學校,中央研究院,國小,國中,高中,高職,專科"
        ).split(",")
        if kw.strip()
    ]

    # 每日爬蟲回溯天數（含今天，例如 3 = 今天 + 前 2 天）
    SCRAPE_LOOKBACK_DAYS = max(1, int(os.getenv("SCRAPE_LOOKBACK_DAYS", "3")))
    BIDDING_LOOKBACK_DAYS = max(1, int(os.getenv("BIDDING_LOOKBACK_DAYS", "3")))

    # 公開招標採購性質篩選（工程/財物/勞務，留空=不限）
    BIDDING_PROC_CATEGORIES = [
        c.strip()
        for c in os.getenv("BIDDING_PROC_CATEGORIES", "").split(",")
        if c.strip()
    ]

    # Discord 每則訊息 Embed 數量上限
    DISCORD_EMBED_BATCH_SIZE = min(10, max(1, int(os.getenv("DISCORD_EMBED_BATCH_SIZE", "5"))))

    # 篩選關鍵字
    FILTER_KEYWORDS = [
        kw.strip()
        for kw in os.getenv(
            "FILTER_KEYWORDS",
            "網路設備,資訊設備,通訊設備,路由器,交換器"
        ).split(",")
        if kw.strip()
    ]

    # Chrome / Chromium（Docker 內建路徑見 docker-compose.yml）
    CHROME_HEADLESS = os.getenv("CHROME_HEADLESS", "true").lower() == "true"
    CHROMIUM_BIN = os.getenv("CHROMIUM_BIN", "").strip()
    CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "").strip()
    PAGE_LOAD_TIMEOUT = int(os.getenv("PAGE_LOAD_TIMEOUT", "90"))

    # 代理（公司網路若需 Proxy 可設定，例如 http://proxy.company:8080）
    HTTP_PROXY = os.getenv("HTTP_PROXY", "").strip()
    HTTPS_PROXY = os.getenv("HTTPS_PROXY", "").strip()

    # 應用
    APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
    APP_PORT = int(os.getenv("APP_PORT", "8000"))

    # 爬蟲設定
    PCC_BASE_URL = "https://web.pcc.gov.tw"
    PCC_SEARCH_URL = f"{PCC_BASE_URL}/prkms/tpAppeal/common/readTpAppeal"
    PCC_INDEX_URL = f"{PCC_BASE_URL}/prkms/tpAppeal/common/indexTpAppeal"
    PCC_BIDDING_SEARCH_URL = (
        f"{PCC_BASE_URL}/prkms/tender/common/basic/readTenderBasic"
    )
    REQUEST_DELAY_MIN = 2  # 最小延遲秒數
    REQUEST_DELAY_MAX = 5  # 最大延遲秒數
    MAX_RETRIES = 3  # 最大重試次數

    # 資料庫
    DATABASE_URL = f"sqlite:///{DB_PATH}"

    @classmethod
    def reload(cls):
        """重新載入環境變數"""
        load_dotenv(cls.BASE_DIR / ".env", override=True, encoding="utf-8")
        cls.DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
        cls.BIDDING_DISCORD_WEBHOOK_URL = os.getenv("BIDDING_DISCORD_WEBHOOK_URL", "")
        cls.SALES_DISCORD_WEBHOOK_URL = os.getenv("SALES_DISCORD_WEBHOOK_URL", "")
        cls.SCRAPE_SCHEDULE_HOUR = int(os.getenv("SCRAPE_SCHEDULE_HOUR", "8"))
        cls.SCRAPE_SCHEDULE_MINUTE = int(os.getenv("SCRAPE_SCHEDULE_MINUTE", "10"))
        cls.BIDDING_SCHEDULE_HOUR = int(os.getenv("BIDDING_SCHEDULE_HOUR", "9"))
        cls.BIDDING_SCHEDULE_MINUTE = int(os.getenv("BIDDING_SCHEDULE_MINUTE", "0"))
        cls.TRACK_CHECK_HOUR = int(os.getenv("TRACK_CHECK_HOUR", "12"))
        cls.TRACK_CHECK_MINUTE = int(os.getenv("TRACK_CHECK_MINUTE", "0"))
        cls.HEALTH_CHECK_HOUR = int(os.getenv("HEALTH_CHECK_HOUR", "8"))
        cls.HEALTH_CHECK_MINUTE = int(os.getenv("HEALTH_CHECK_MINUTE", "0"))
        cls.JOB104_SCHEDULE_HOUR = int(os.getenv("JOB104_SCHEDULE_HOUR", "10"))
        cls.JOB104_SCHEDULE_MINUTE = int(os.getenv("JOB104_SCHEDULE_MINUTE", "0"))
        cls.SALES_SUMMARY_HOUR = int(os.getenv("SALES_SUMMARY_HOUR", "17"))
        cls.SALES_SUMMARY_MINUTE = int(os.getenv("SALES_SUMMARY_MINUTE", "0"))
        cls.JOB104_SKIP_KEYWORDS = [
            kw.strip()
            for kw in os.getenv(
                "JOB104_SKIP_KEYWORDS",
                "大學,學院,學校,中央研究院,國小,國中,高中,高職,專科"
            ).split(",")
            if kw.strip()
        ]
        cls.SCRAPE_LOOKBACK_DAYS = max(1, int(os.getenv("SCRAPE_LOOKBACK_DAYS", "3")))
        cls.BIDDING_LOOKBACK_DAYS = max(1, int(os.getenv("BIDDING_LOOKBACK_DAYS", "3")))
        cls.BIDDING_PROC_CATEGORIES = [
            c.strip()
            for c in os.getenv("BIDDING_PROC_CATEGORIES", "").split(",")
            if c.strip()
        ]
        cls.DISCORD_EMBED_BATCH_SIZE = min(
            10, max(1, int(os.getenv("DISCORD_EMBED_BATCH_SIZE", "5")))
        )
        cls.FILTER_KEYWORDS = [
            kw.strip()
            for kw in os.getenv(
                "FILTER_KEYWORDS",
                "網路設備,資訊設備,通訊設備,路由器,交換器"
            ).split(",")
            if kw.strip()
        ]
        cls.DATA_DIR = Path(os.getenv("DATA_DIR", str(cls.BASE_DIR)))
        cls.DB_PATH = cls.DATA_DIR / "database.db"
        cls.LOG_DIR = cls.DATA_DIR / "logs"
        cls.LOG_FILE = cls.LOG_DIR / "scraper.log"
        cls.DATABASE_URL = f"sqlite:///{cls.DB_PATH}"
        cls.CHROME_HEADLESS = os.getenv("CHROME_HEADLESS", "true").lower() == "true"
        cls.CHROMIUM_BIN = os.getenv("CHROMIUM_BIN", "").strip()
        cls.CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "").strip()
        cls.PAGE_LOAD_TIMEOUT = int(os.getenv("PAGE_LOAD_TIMEOUT", "90"))
        cls.HTTP_PROXY = os.getenv("HTTP_PROXY", "").strip()
        cls.HTTPS_PROXY = os.getenv("HTTPS_PROXY", "").strip()


config = Config()
