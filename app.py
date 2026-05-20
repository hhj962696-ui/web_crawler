"""
FastAPI 主應用程式
提供 Web UI 與 API 路由
"""

import os
import logging
from datetime import datetime, date
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from config import config
from models import init_db, get_db, Tender, ScrapeLog, SessionLocal
from scheduler import (
    manual_run_scraper, manual_check_tracked,
    is_scraper_running, get_next_run_times,
)
from discord_notifier import send_test_notification

logger = logging.getLogger(__name__)

# === FastAPI 應用 ===
app = FastAPI(
    title="政府採購爬蟲系統",
    description="政府電子採購網公開徵求案件自動擷取系統",
    version="1.0.0",
)

# 靜態檔案與模板
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# 每頁顯示筆數
PAGE_SIZE = 20


# === 工具函式 ===
def _get_stats(db: Session) -> dict:
    """取得統計數據"""
    total = db.query(func.count(Tender.id)).scalar() or 0
    today_start = datetime.combine(date.today(), datetime.min.time())
    today = db.query(func.count(Tender.id)).filter(
        Tender.created_at >= today_start
    ).scalar() or 0
    tracked = db.query(func.count(Tender.id)).filter(
        Tender.is_tracked == True
    ).scalar() or 0

    last_log = db.query(ScrapeLog).filter(
        ScrapeLog.status == "success"
    ).order_by(desc(ScrapeLog.finished_at)).first()
    last_scrape = last_log.finished_at.strftime("%m/%d %H:%M") if last_log and last_log.finished_at else None

    return {
        "total": total,
        "today": today,
        "tracked": tracked,
        "last_scrape": last_scrape,
    }


# === Web UI 路由 ===

@app.get("/")
async def index_page(request: Request, page: int = 1):
    """首頁 — 全部案件列表"""
    db = SessionLocal()
    try:
        stats = _get_stats(db)

        offset = (page - 1) * PAGE_SIZE
        query = db.query(Tender).order_by(desc(Tender.created_at))
        total_count = query.count()
        tenders = query.offset(offset).limit(PAGE_SIZE).all()
        total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)

        return templates.TemplateResponse("index.html", {
            "request": request,
            "active_page": "index",
            "tenders": [t.to_dict() for t in tenders],
            "stats": stats,
            "page": page,
            "total_pages": total_pages,
            "tracked_count": stats["tracked"],
        })
    finally:
        db.close()


@app.get("/tracked")
async def tracked_page(request: Request):
    """追蹤案件頁面"""
    db = SessionLocal()
    try:
        tracked_tenders = db.query(Tender).filter(
            Tender.is_tracked == True
        ).order_by(desc(Tender.updated_at)).all()

        status_changed_count = len([
            t for t in tracked_tenders if t.status != "公開徵求"
        ])

        return templates.TemplateResponse("tracked.html", {
            "request": request,
            "active_page": "tracked",
            "tracked_tenders": [t.to_dict() for t in tracked_tenders],
            "status_changed_count": status_changed_count,
            "tracked_count": len(tracked_tenders),
        })
    finally:
        db.close()


@app.get("/settings")
async def settings_page(request: Request):
    """系統設定頁面"""
    db = SessionLocal()
    try:
        scrape_logs = db.query(ScrapeLog).order_by(
            desc(ScrapeLog.started_at)
        ).limit(20).all()

        next_runs = get_next_run_times()
        webhook_url = config.DISCORD_WEBHOOK_URL
        webhook_masked = webhook_url[:40] + "..." if len(webhook_url) > 40 else webhook_url

        tracked_count = db.query(func.count(Tender.id)).filter(
            Tender.is_tracked == True
        ).scalar() or 0

        return templates.TemplateResponse("settings.html", {
            "request": request,
            "active_page": "settings",
            "keywords": config.FILTER_KEYWORDS,
            "schedule": {
                "scrape_hour": config.SCRAPE_SCHEDULE_HOUR,
                "scrape_minute": config.SCRAPE_SCHEDULE_MINUTE,
                "track_hour": config.TRACK_CHECK_HOUR,
                "track_minute": config.TRACK_CHECK_MINUTE,
            },
            "next_runs": next_runs,
            "webhook_masked": webhook_masked,
            "scrape_logs": [log.to_dict() for log in scrape_logs],
            "tracked_count": tracked_count,
        })
    finally:
        db.close()


# === API 路由 ===

@app.get("/api/stats")
async def api_stats():
    """取得統計數據"""
    db = SessionLocal()
    try:
        return _get_stats(db)
    finally:
        db.close()


@app.get("/api/tenders")
async def api_tenders(
    page: int = 1,
    status: str = None,
    tracked: str = None,
    search: str = None,
    sort: str = "newest",
):
    """取得案件列表 (JSON)"""
    db = SessionLocal()
    try:
        query = db.query(Tender)

        if status:
            query = query.filter(Tender.status == status)
        if tracked == "true":
            query = query.filter(Tender.is_tracked == True)
        elif tracked == "false":
            query = query.filter(Tender.is_tracked == False)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                (Tender.tender_name.like(pattern)) |
                (Tender.tender_id.like(pattern)) |
                (Tender.org_name.like(pattern))
            )

        if sort == "oldest":
            query = query.order_by(Tender.created_at)
        elif sort == "budget_high":
            query = query.order_by(desc(Tender.budget))
        elif sort == "budget_low":
            query = query.order_by(Tender.budget)
        else:
            query = query.order_by(desc(Tender.created_at))

        total = query.count()
        offset = (page - 1) * PAGE_SIZE
        tenders = query.offset(offset).limit(PAGE_SIZE).all()

        return {
            "tenders": [t.to_dict() for t in tenders],
            "total": total,
            "page": page,
            "total_pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        }
    finally:
        db.close()


@app.post("/api/tenders/{tender_db_id}/track")
async def api_toggle_track(tender_db_id: int):
    """切換追蹤狀態"""
    db = SessionLocal()
    try:
        tender = db.query(Tender).filter_by(id=tender_db_id).first()
        if not tender:
            return JSONResponse({"success": False, "message": "案件不存在"}, status_code=404)

        tender.is_tracked = not tender.is_tracked
        tender.updated_at = datetime.now()
        db.commit()

        return {
            "success": True,
            "is_tracked": tender.is_tracked,
            "message": "已加入追蹤" if tender.is_tracked else "已取消追蹤",
        }
    finally:
        db.close()


@app.put("/api/tenders/{tender_db_id}/note")
async def api_update_note(tender_db_id: int, request: Request):
    """更新追蹤備註"""
    db = SessionLocal()
    try:
        body = await request.json()
        tender = db.query(Tender).filter_by(id=tender_db_id).first()
        if not tender:
            return JSONResponse({"success": False, "message": "案件不存在"}, status_code=404)

        tender.track_note = body.get("note", "")
        tender.updated_at = datetime.now()
        db.commit()

        return {"success": True, "message": "備註已更新"}
    finally:
        db.close()


@app.post("/api/scrape/run")
async def api_scrape_run():
    """手動觸發爬蟲"""
    result = manual_run_scraper()
    return result


@app.post("/api/scrape/check-tracked")
async def api_check_tracked():
    """手動觸發追蹤檢查"""
    result = manual_check_tracked()
    return result


@app.get("/api/scrape/status")
async def api_scrape_status():
    """查詢爬蟲執行狀態"""
    return {"is_running": is_scraper_running()}


@app.get("/api/scrape/logs")
async def api_scrape_logs(limit: int = 20):
    """取得爬蟲執行紀錄"""
    db = SessionLocal()
    try:
        logs = db.query(ScrapeLog).order_by(
            desc(ScrapeLog.started_at)
        ).limit(limit).all()
        return {"logs": [log.to_dict() for log in logs]}
    finally:
        db.close()


@app.get("/api/schedule/info")
async def api_schedule_info():
    """取得排程資訊"""
    next_runs = get_next_run_times()
    next_scrape = None
    for job_id, info in next_runs.items():
        if "daily" in job_id:
            next_scrape = info["next_run"]
            break
    return {
        "jobs": next_runs,
        "next_scrape": next_scrape,
        "is_running": is_scraper_running(),
    }


@app.post("/api/settings/keywords")
async def api_add_keyword(request: Request):
    """新增篩選關鍵字"""
    body = await request.json()
    keyword = body.get("keyword", "").strip()
    if not keyword:
        return {"success": False, "message": "關鍵字不能為空"}
    if keyword in config.FILTER_KEYWORDS:
        return {"success": False, "message": "關鍵字已存在"}

    config.FILTER_KEYWORDS.append(keyword)
    _save_keywords_to_env()
    return {"success": True, "keywords": config.FILTER_KEYWORDS}


@app.delete("/api/settings/keywords")
async def api_remove_keyword(request: Request):
    """移除篩選關鍵字"""
    body = await request.json()
    keyword = body.get("keyword", "").strip()
    if keyword in config.FILTER_KEYWORDS:
        config.FILTER_KEYWORDS.remove(keyword)
        _save_keywords_to_env()
        return {"success": True, "keywords": config.FILTER_KEYWORDS}
    return {"success": False, "message": "關鍵字不存在"}


@app.put("/api/settings/schedule")
async def api_update_schedule(request: Request):
    """更新排程設定"""
    body = await request.json()
    try:
        config.SCRAPE_SCHEDULE_HOUR = int(body.get("scrape_hour", config.SCRAPE_SCHEDULE_HOUR))
        config.SCRAPE_SCHEDULE_MINUTE = int(body.get("scrape_minute", config.SCRAPE_SCHEDULE_MINUTE))
        config.TRACK_CHECK_HOUR = int(body.get("track_hour", config.TRACK_CHECK_HOUR))
        config.TRACK_CHECK_MINUTE = int(body.get("track_minute", config.TRACK_CHECK_MINUTE))
        _save_schedule_to_env()
        return {"success": True, "message": "排程設定已儲存（重啟後生效）"}
    except (ValueError, TypeError) as e:
        return {"success": False, "message": f"無效的時間設定: {e}"}


@app.post("/api/settings/test-webhook")
async def api_test_webhook():
    """測試 Discord Webhook"""
    success = send_test_notification()
    return {
        "success": success,
        "message": "測試通知已發送！" if success else "發送失敗，請檢查 Webhook URL",
    }


# === 工具函式 ===
def _save_keywords_to_env():
    """將關鍵字儲存到 .env 檔案"""
    _update_env_value("FILTER_KEYWORDS", ",".join(config.FILTER_KEYWORDS))


def _save_schedule_to_env():
    """將排程設定儲存到 .env 檔案"""
    _update_env_value("SCRAPE_SCHEDULE_HOUR", str(config.SCRAPE_SCHEDULE_HOUR))
    _update_env_value("SCRAPE_SCHEDULE_MINUTE", str(config.SCRAPE_SCHEDULE_MINUTE))
    _update_env_value("TRACK_CHECK_HOUR", str(config.TRACK_CHECK_HOUR))
    _update_env_value("TRACK_CHECK_MINUTE", str(config.TRACK_CHECK_MINUTE))


def _update_env_value(key: str, value: str):
    """更新 .env 檔案中的特定鍵值"""
    env_path = config.BASE_DIR / ".env"
    if not env_path.exists():
        return

    lines = env_path.read_text(encoding="utf-8").splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            updated = True
            break

    if not updated:
        lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
