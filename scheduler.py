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
from bidding_scraper import run_bidding_scraper
from discord_notifier import send_daily_health_check_notification
from job_analyzer import run_batch_analysis

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="Asia/Taipei")

_scraper_lock = threading.Lock()
_running_mode = None  # None | "appeal" | "bidding" | "track"


def _safe_run_scraper(scrape_type: str = "daily"):
    global _running_mode
    if _running_mode:
        logger.warning(f"爬蟲正在執行中（{_running_mode}），跳過此次排程")
        return

    with _scraper_lock:
        _running_mode = "appeal"
        try:
            logger.info(f"[排程] 開始執行 {scrape_type} 公開徵求爬蟲...")
            result = run_scraper(scrape_type=scrape_type)
            logger.info(f"[排程] {scrape_type} 公開徵求完成: {result}")
        except Exception as e:
            logger.error(f"[排程] 公開徵求爬蟲異常: {e}", exc_info=True)
        finally:
            _running_mode = None


def _safe_run_bidding_scraper(scrape_type: str = "bidding_daily"):
    global _running_mode
    if _running_mode:
        logger.warning(f"爬蟲正在執行中（{_running_mode}），跳過此次排程")
        return

    with _scraper_lock:
        _running_mode = "bidding"
        try:
            logger.info(f"[排程] 開始執行 {scrape_type} 公開招標爬蟲...")
            result = run_bidding_scraper(scrape_type=scrape_type)
            logger.info(f"[排程] {scrape_type} 公開招標完成: {result}")
        except Exception as e:
            logger.error(f"[排程] 公開招標爬蟲異常: {e}", exc_info=True)
        finally:
            _running_mode = None


def _safe_check_tracked():
    global _running_mode
    if _running_mode:
        logger.warning("爬蟲正在執行中，跳過追蹤檢查")
        return

    with _scraper_lock:
        _running_mode = "track"
        try:
            logger.info("[排程] 開始檢查追蹤案件...")
            result = check_tracked_tenders()
            logger.info(f"[排程] 追蹤檢查完成: {result}")
        except Exception as e:
            logger.error(f"[排程] 追蹤檢查異常: {e}", exc_info=True)
        finally:
            _running_mode = None


def _safe_health_check():
    logger.info("[排程] 開始發送每日運作檢測通知...")
    success = send_daily_health_check_notification()
    if success:
        logger.info("[排程] 每日運作檢測通知發送成功")
    else:
        logger.error("[排程] 每日運作檢測通知發送失敗")


def _safe_run_job_analyzer():
    global _running_mode
    if _running_mode:
        logger.warning(f"爬蟲正在執行中（{_running_mode}），跳過 104 分析排程")
        return

    with _scraper_lock:
        _running_mode = "job104"
        try:
            logger.info("[排程] 開始執行 104 探測器批次分析...")
            result = run_batch_analysis()
            logger.info(f"[排程] 104 探測器分析完成: {result}")
        except Exception as e:
            logger.error(f"[排程] 104 探測器異常: {e}", exc_info=True)
        finally:
            _running_mode = None


def is_scraper_running() -> bool:
    return _running_mode is not None


def get_running_mode():
    return _running_mode


def manual_run_scraper() -> dict:
    if _running_mode:
        return {"started": False, "message": f"爬蟲正在執行中（{_running_mode}），請稍後再試"}

    thread = threading.Thread(
        target=_safe_run_scraper,
        args=("manual",),
        daemon=True,
    )
    thread.start()
    return {"started": True, "message": "公開徵求爬蟲已開始執行，請稍候查看結果"}


def manual_run_bidding_scraper() -> dict:
    if _running_mode:
        return {"started": False, "message": f"爬蟲正在執行中（{_running_mode}），請稍後再試"}

    thread = threading.Thread(
        target=_safe_run_bidding_scraper,
        args=("bidding_manual",),
        daemon=True,
    )
    thread.start()
    return {"started": True, "message": "公開招標爬蟲已開始執行，請稍候查看結果"}


def manual_check_tracked() -> dict:
    if _running_mode:
        return {"started": False, "message": f"爬蟲正在執行中（{_running_mode}），請稍後再試"}

    thread = threading.Thread(
        target=_safe_check_tracked,
        daemon=True,
    )
    thread.start()
    return {"started": True, "message": "追蹤檢查已開始執行"}


def manual_run_job_analyzer() -> dict:
    if _running_mode:
        return {"started": False, "message": f"系統忙碌中（{_running_mode}），請稍後再試"}

    thread = threading.Thread(
        target=_safe_run_job_analyzer,
        daemon=True,
    )
    thread.start()
    return {"started": True, "message": "104 探測器已開始執行，請稍候查看分析紀錄"}


def _register_jobs():
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

    scheduler.add_job(
        _safe_run_bidding_scraper,
        CronTrigger(
            hour=config.BIDDING_SCHEDULE_HOUR,
            minute=config.BIDDING_SCHEDULE_MINUTE,
        ),
        id="daily_bidding_scraper",
        name="每日公開招標爬蟲",
        replace_existing=True,
        kwargs={"scrape_type": "bidding_daily"},
    )

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

    scheduler.add_job(
        _safe_health_check,
        CronTrigger(
            hour=config.HEALTH_CHECK_HOUR,
            minute=config.HEALTH_CHECK_MINUTE,
        ),
        id="health_checker",
        name="每日運作檢測",
        replace_existing=True,
    )

    scheduler.add_job(
        _safe_run_job_analyzer,
        CronTrigger(
            hour=config.JOB104_SCHEDULE_HOUR,
            minute=config.JOB104_SCHEDULE_MINUTE,
        ),
        id="job104_analyzer",
        name="104 人力銀行探測器",
        replace_existing=True,
    )


def init_scheduler():
    _register_jobs()
    if not scheduler.running:
        scheduler.start()
    logger.info(
        f"排程器已啟動 — "
        f"公開徵求: {config.SCRAPE_SCHEDULE_HOUR:02d}:{config.SCRAPE_SCHEDULE_MINUTE:02d} "
        f"(回溯 {config.SCRAPE_LOOKBACK_DAYS} 天), "
        f"公開招標: {config.BIDDING_SCHEDULE_HOUR:02d}:{config.BIDDING_SCHEDULE_MINUTE:02d} "
        f"(回溯 {config.BIDDING_LOOKBACK_DAYS} 天), "
        f"追蹤檢查: {config.TRACK_CHECK_HOUR:02d}:{config.TRACK_CHECK_MINUTE:02d}, "
        f"運作檢測: {config.HEALTH_CHECK_HOUR:02d}:{config.HEALTH_CHECK_MINUTE:02d}, "
        f"104 探測: {config.JOB104_SCHEDULE_HOUR:02d}:{config.JOB104_SCHEDULE_MINUTE:02d}"
    )


def reschedule_jobs():
    if not scheduler.running:
        init_scheduler()
        return
    _register_jobs()
    logger.info("排程已更新")


def get_next_run_times() -> dict:
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
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("排程器已關閉")
