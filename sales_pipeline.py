"""
業務分析觸發管線
串接 模組 A（104 探測）→ 模組 B（設備匹配）→ 模組 C（報價引擎）

觸發策略：
- 公開徵求入庫 → 僅觸發模組 A
- 公開招標入庫 → 觸發模組 A + B + C
"""

import logging
import threading
from datetime import datetime

from models import SessionLocal, SalesInsight, AnalysisLog

logger = logging.getLogger(__name__)


def _ensure_insight_row(db, tender_id: str, source_table: str, org_name: str) -> SalesInsight:
    """確保 sales_insights 表中有該案號的記錄，沒有則新建"""
    row = db.query(SalesInsight).filter_by(tender_id=tender_id).first()
    if not row:
        row = SalesInsight(
            tender_id=tender_id,
            source_table=source_table,
            org_name=org_name,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    elif org_name and not row.org_name:
        row.org_name = org_name
        row.updated_at = datetime.now()
        db.commit()
    return row


def _run_module_a(db, insight: SalesInsight) -> None:
    """模組 A：104 人力銀行遠端工作探測（階段 2 實作）"""
    from job_analyzer import analyze_single_tender
    logger.info(f"[Pipeline] 執行模組 A (104探測): {insight.tender_id}")
    analyze_single_tender(db, insight)


def _run_module_b(db, insight: SalesInsight) -> None:
    """模組 B：需求計算與設備匹配（階段 4 實作）"""
    log = AnalysisLog(
        tender_id=insight.tender_id,
        module="device",
        status="skipped",
        message="模組 B 尚未實作（階段 4）",
        started_at=datetime.now(),
        finished_at=datetime.now(),
    )
    db.add(log)
    db.commit()
    logger.debug(f"[Pipeline] 模組 B 略過（尚未實作）: {insight.tender_id}")


def _run_module_c(db, insight: SalesInsight) -> None:
    """模組 C：動態比價與報價引擎（階段 5 實作）"""
    log = AnalysisLog(
        tender_id=insight.tender_id,
        module="pricing",
        status="skipped",
        message="模組 C 尚未實作（階段 5）",
        started_at=datetime.now(),
        finished_at=datetime.now(),
    )
    db.add(log)
    db.commit()
    logger.debug(f"[Pipeline] 模組 C 略過（尚未實作）: {insight.tender_id}")


def _run_pipeline(tender_id: str, source_table: str, org_name: str, modules: list[str]):
    """在背景執行分析管線（由 thread 呼叫）"""
    db = SessionLocal()
    try:
        # 自動同步聯絡人 (階段 3)
        from contact_manager import sync_contacts_from_tenders
        sync_contacts_from_tenders(tender_id, source_table)

        insight = _ensure_insight_row(db, tender_id, source_table, org_name)

        if "A" in modules:
            _run_module_a(db, insight)
        if "B" in modules:
            _run_module_b(db, insight)
        if "C" in modules:
            _run_module_c(db, insight)

        logger.info(
            f"[Pipeline] 分析完成 tender_id={tender_id} "
            f"modules={modules} source={source_table}"
        )
    except Exception as e:
        logger.error(f"[Pipeline] 分析異常 tender_id={tender_id}: {e}", exc_info=True)
    finally:
        db.close()


def trigger_analysis(
    tender_id: str,
    source_table: str = "tenders",
    org_name: str = "",
    modules: list[str] | None = None,
) -> None:
    """
    觸發業務分析管線（非同步，不阻塞爬蟲主流程）

    Args:
        tender_id: 案號
        source_table: 來源表 ('tenders' | 'bidding_tenders')
        org_name: 機關名稱
        modules: 要執行的模組列表，預設依 source_table 自動判斷
    """
    if not tender_id:
        return

    if modules is None:
        if source_table == "bidding_tenders":
            modules = ["A", "B", "C"]
        else:
            modules = ["A"]

    thread = threading.Thread(
        target=_run_pipeline,
        args=(tender_id, source_table, org_name, modules),
        daemon=True,
    )
    thread.start()
    logger.debug(f"[Pipeline] 已觸發分析 tender_id={tender_id} modules={modules}")
