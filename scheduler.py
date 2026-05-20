"""
排程管理模組
使用 APScheduler 管理每日爬蟲與追蹤檢查排程
"""

import logging
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import config
from scraper import run_scraper, check_tracked_tenders

logger = logging.getLogger(__name__)

# 全域排程器
scheduler = BackgroundScheduler(timezone="Asia/Taipei")

# 爬蟲執行鎖（避免同時執行多個爬蟲）
_scraper_lock = threading.Lock()
_is_running = False


def _safe_run_scraper(scrape_type: str = "daily"):
    """安全執行爬蟲（帶鎖機制）"""
    global _is_running
    if _is_running:
        logger.warning("爬蟲正在執行中，跳過此次排程")
        return

    with _scraper_lock:
        _is_running = True
        try:
            logger.info(f"[排程] 開始執行 {scrape_type} 爬蟲...")
            result = run_scraper(scrape_type=scrape_type)
            logger.info(f"[排程] {scrape_type} 爬蟲完成: {result}")
        except Exception as e:
            logger.error(f"[排程] 爬蟲執行異常: {e}", exc_info=True)
        finally:
            _is_running = False


def _safe_check_tracked():
    """安全執行追蹤檢查"""
    global _is_running
    if _is_running:
        logger.warning("爬蟲正在執行中，跳過追蹤檢查")
        return

    with _scraper_lock:
        _is_running = True
        try:
            logger.info("[排程] 開始檢查追蹤案件...")
            result = check_tracked_tenders()
            logger.info(f"[排程] 追蹤檢查完成: {result}")
        except Exception as e:
            logger.error(f"[排程] 追蹤檢查異常: {e}", exc_info=True)
        finally:
            _is_running = False


def is_scraper_running() -> bool:
    """檢查爬蟲是否正在執行"""
    return _is_running


def manual_run_scraper() -> dict:
    """
    手動觸發爬蟲（非阻塞）

    Returns:
        dict: {"started": bool, "message": str}
    """
    if _is_running:
        return {"started": False, "message": "爬蟲正在執行中，請稍後再試"}

    thread = threading.Thread(
        target=_safe_run_scraper,
        args=("manual",),
        daemon=True,
    )
    thread.start()
    return {"started": True, "message": "爬蟲已開始執行，請稍候查看結果"}


def manual_check_tracked() -> dict:
    """手動觸發追蹤檢查（非阻塞）"""
    if _is_running:
        return {"started": False, "message": "爬蟲正在執行中，請稍後再試"}

    thread = threading.Thread(
        target=_safe_check_tracked,
        daemon=True,
    )
    thread.start()
    return {"started": True, "message": "追蹤檢查已開始執行"}


def init_scheduler():
    """初始化排程器"""
    # 每日爬蟲排程
    scheduler.add_job(
        _safe_run_scraper,
        CronTrigger(
            hour=config.SCRAPE_SCHEDULE_HOUR,
            minute=config.SCRAPE_SCHEDULE_MINUTE,
        ),
        id="daily_scraper",
        name="每日公開徵求爬蟲",
        replace_existing=True,
        kwargs={"scrape_type": "daily"},
    )

    # 追蹤案件檢查排程
    scheduler.add_job(
        _safe_check_tracked,
        CronTrigger(
            hour=config.TRACK_CHECK_HOUR,
            minute=config.TRACK_CHECK_MINUTE,
        ),
        id="track_checker",
        name="追蹤案件狀態檢查",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        f"排程器已啟動 — "
        f"每日爬蟲: {config.SCRAPE_SCHEDULE_HOUR:02d}:{config.SCRAPE_SCHEDULE_MINUTE:02d}, "
        f"追蹤檢查: {config.TRACK_CHECK_HOUR:02d}:{config.TRACK_CHECK_MINUTE:02d}"
    )


def get_next_run_times() -> dict:
    """取得下次排程執行時間"""
    jobs = scheduler.get_jobs()
    result = {}
    for job in jobs:
        next_run = job.next_run_time
        result[job.id] = {
            "name": job.name,
            "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else "未排程",
        }
    return result


def shutdown_scheduler():
    """關閉排程器"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("排程器已關閉")
