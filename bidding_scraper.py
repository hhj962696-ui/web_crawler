"""
公開招標爬蟲模組
擷取政府電子採購網「招標查詢」中「公開招標」公告
"""

import logging
import re
from datetime import datetime, date, timedelta

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    StaleElementReferenceException,
)

from config import config
from models import SessionLocal, Tender, BiddingTender, ScrapeLog
from time_utils import now_tw, format_tw, discord_timestamp
from scraper import (
    _create_driver,
    _random_delay,
    _dedupe_tenders,
    _matches_keywords,
    _needs_detail_enrichment,
    _should_overwrite_field,
    _phone_field_is_corrupt,
    _sanitize_phone_for_storage,
    _parse_detail_page,
    _load_detail_page,
)
from discord_notifier import (
    send_new_bidding_notification,
    send_bidding_error_notification,
)

logger = logging.getLogger(__name__)

BIDDING_DETAIL_MARKERS = ("urlSelector/common/tpam", "readTenderBasic")
BIDDING_STATUS = "公開招標"

# 採購性質設定值 → 列表欄位顯示文字
PROC_CATEGORY_LABELS = {
    "工程": "工程類",
    "財物": "財物類",
    "勞務": "勞務類",
}


def _get_bidding_date_range(
    custom_start_date: str = None,
    custom_end_date: str = None,
) -> tuple[str, str]:
    today = date.today()
    if custom_start_date and custom_end_date:
        return custom_start_date, custom_end_date
    lookback = config.BIDDING_LOOKBACK_DAYS
    start = today - timedelta(days=lookback - 1)
    return start.strftime("%Y/%m/%d"), today.strftime("%Y/%m/%d")


def _build_bidding_search_url(start_date: str, end_date: str) -> str:
    params = {
        "pageSize": "",
        "firstSearch": "true",
        "searchType": "basic",
        "isBinding": "N",
        "isLogIn": "N",
        "orgName": "",
        "orgId": "",
        "tenderName": "",
        "tenderId": "",
        "tenderType": "TENDER_DECLARATION",
        "tenderWay": "TENDER_WAY_1",
        "dateType": "isDate",
        "tenderStartDate": start_date,
        "tenderEndDate": end_date,
        "radProctrgCate": "",
        "policyAdvocacy": "",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{config.PCC_BIDDING_SEARCH_URL}?{query}"


def _normalize_detail_url(href: str) -> str:
    if not href:
        return ""
    href = href.strip()
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"{config.PCC_BASE_URL}{href}"
    return f"{config.PCC_BASE_URL}/{href.lstrip('/')}"


def _extract_bidding_detail_url(row) -> str:
    for link in row.find_all("a", href=True):
        href = link.get("href", "")
        if any(marker in href for marker in BIDDING_DETAIL_MARKERS):
            return _normalize_detail_url(href)
        title = (link.get("title") or "") + (link.get_text(strip=True) or "")
        if "檢視" in title or re.match(r"^\d{1,2}$", link.get_text(strip=True)):
            return _normalize_detail_url(href)
    return ""


def _split_case_id_and_name(text: str) -> tuple[str, str]:
    """從「案號 (更正公告)」等合併欄位拆出案號與案名"""
    text = (text or "").strip()
    if not text:
        return "", ""
    match = re.match(r"^([A-Za-z0-9\-_.]+)", text)
    if match:
        tid = match.group(1)
        rest = text[len(match.group(0)):].strip()
        name = re.sub(r"^[\s\-–—()（）]*", "", rest).strip()
        return tid, name or text
    return "", text


def _parse_bidding_table_rows(page_source: str) -> list[dict]:
    soup = BeautifulSoup(page_source, "html.parser")
    results = []

    table = soup.find("table", class_="tb_01")
    if not table:
        for t in soup.find_all("table"):
            if t.find("th") and ("案號" in t.get_text() or "標案案號" in t.get_text()):
                table = t
                break

    if not table:
        logger.warning("公開招標：找不到結果表格")
        return results

    rows = table.find_all("tr")
    if len(rows) < 2:
        return results

    header_row = rows[0]
    headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
    col_map: dict[str, int] = {}
    for i, h in enumerate(headers):
        if "機關" in h and "代碼" not in h:
            col_map["org_name"] = i
        elif "案號" in h or "標案名稱" in h:
            col_map["case_cell"] = i
        elif "招標方式" in h:
            col_map["tender_way"] = i
        elif "採購性質" in h:
            col_map["proctrg_cate"] = i
        elif "公告日期" in h:
            col_map["announce_date"] = i
        elif "截止" in h:
            col_map["bid_deadline"] = i
        elif "預算" in h or "金額" in h:
            col_map["budget"] = i

    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        tender = {
            "tender_id": "",
            "tender_name": "",
            "org_name": "",
            "contact_person": "",
            "phone": "",
            "budget": "",
            "tender_url": "",
            "status": BIDDING_STATUS,
            "proctrg_cate": "",
            "bid_deadline": "",
            "tender_way": "",
        }

        if "org_name" in col_map and col_map["org_name"] < len(cells):
            tender["org_name"] = cells[col_map["org_name"]].get_text(strip=True)

        if "case_cell" in col_map and col_map["case_cell"] < len(cells):
            case_text = cells[col_map["case_cell"]].get_text(" ", strip=True)
            tid, tname = _split_case_id_and_name(case_text)
            tender["tender_id"] = tid
            tender["tender_name"] = tname

        for field in ("tender_way", "proctrg_cate", "bid_deadline", "budget"):
            if field in col_map and col_map[field] < len(cells):
                tender[field] = cells[col_map[field]].get_text(strip=True)

        # 無表頭對應時依常見欄位順序推測
        if not tender["tender_id"] and len(cells) >= 8:
            tender["org_name"] = tender["org_name"] or cells[1].get_text(strip=True)
            case_text = cells[2].get_text(" ", strip=True)
            tid, tname = _split_case_id_and_name(case_text)
            tender["tender_id"] = tid
            tender["tender_name"] = tname
            tender["tender_way"] = tender["tender_way"] or cells[4].get_text(strip=True)
            tender["proctrg_cate"] = tender["proctrg_cate"] or cells[5].get_text(strip=True)
            tender["bid_deadline"] = tender["bid_deadline"] or cells[7].get_text(strip=True)
            if len(cells) > 8:
                tender["budget"] = tender["budget"] or cells[8].get_text(strip=True)

        detail_url = _extract_bidding_detail_url(row)
        if detail_url:
            tender["tender_url"] = detail_url

        if tender["tender_id"] or tender["tender_name"]:
            results.append(tender)

    return results


def _matches_proc_category(tender: dict, categories: list[str]) -> bool:
    if not categories:
        return True
    cate = tender.get("proctrg_cate", "")
    for cat in categories:
        label = PROC_CATEGORY_LABELS.get(cat, cat)
        if label in cate or cat in cate:
            return True
    return False


def _enrich_bidding_from_detail(driver, tender: dict) -> dict:
    url = tender.get("tender_url", "").strip()
    if not url:
        return tender
    try:
        page_source = _load_detail_page(driver, url)
        detail = _parse_detail_page(page_source)
        for field in ("tender_name", "contact_person", "phone", "budget", "org_name"):
            value = detail.get(field, "").strip()
            if not value:
                continue
            existing = tender.get(field, "").strip()
            if field == "phone":
                if _should_overwrite_field("phone", existing, value):
                    tender[field] = value
            elif not existing:
                tender[field] = value
        if not tender.get("status"):
            tender["status"] = detail.get("status") or BIDDING_STATUS
    except Exception as e:
        logger.warning(f"公開招標詳情補抓失敗 [{tender.get('tender_id')}]: {e}")
    return tender


def _sync_appeal_tender(db, tender_data: dict, scraped_now) -> bool:
    """
    若案號已存在公開徵求表，更新為公開招標（同一筆）。
    回傳是否找到並更新。
    """
    tid = tender_data.get("tender_id", "").strip()
    if not tid:
        return False

    existing = db.query(Tender).filter_by(tender_id=tid).first()
    if not existing:
        return False

    existing.status = BIDDING_STATUS
    for field in ("tender_name", "org_name", "contact_person", "phone", "budget", "tender_url"):
        new_val = tender_data.get(field, "").strip()
        if new_val:
            setattr(existing, field, new_val)
    existing.updated_at = scraped_now.replace(tzinfo=None)
    return True


def _upsert_bidding_row(db, tender_data: dict, scraped_now) -> tuple[bool, bool]:
    """
    寫入 bidding_tenders。
    回傳 (is_new, was_updated)
    """
    tid = tender_data.get("tender_id", "").strip()
    existing = db.query(BiddingTender).filter_by(tender_id=tid).first()
    if existing:
        changed = False
        for field in (
            "tender_name", "org_name", "contact_person", "phone", "budget",
            "tender_url", "status", "proctrg_cate", "bid_deadline", "tender_way",
        ):
            new_val = tender_data.get(field, "").strip()
            if field == "phone" and new_val:
                new_val = _sanitize_phone_for_storage(new_val)
            if new_val and new_val != getattr(existing, field, ""):
                setattr(existing, field, new_val)
                changed = True
        if changed:
            existing.updated_at = scraped_now.replace(tzinfo=None)
        return False, changed

    db.add(BiddingTender(
        tender_id=tid,
        tender_name=tender_data.get("tender_name", "").strip(),
        org_name=tender_data.get("org_name", "").strip(),
        contact_person=tender_data.get("contact_person", "").strip(),
        phone=_sanitize_phone_for_storage(tender_data.get("phone", "")),
        budget=tender_data.get("budget", "").strip(),
        tender_url=tender_data.get("tender_url", "").strip(),
        status=tender_data.get("status", BIDDING_STATUS) or BIDDING_STATUS,
        proctrg_cate=tender_data.get("proctrg_cate", "").strip(),
        bid_deadline=tender_data.get("bid_deadline", "").strip(),
        tender_way=tender_data.get("tender_way", "").strip(),
        scraped_at=scraped_now.replace(tzinfo=None),
        created_at=scraped_now.replace(tzinfo=None),
        updated_at=scraped_now.replace(tzinfo=None),
    ))
    return True, False


def run_bidding_scraper(
    scrape_type: str = "bidding_daily",
    use_filter: bool = True,
    custom_start_date: str = None,
    custom_end_date: str = None,
) -> dict:
    db = SessionLocal()
    log = ScrapeLog(
        started_at=datetime.now(),
        scrape_type=scrape_type,
        status="running",
    )
    db.add(log)
    db.commit()

    driver = None
    result = {
        "success": False,
        "new_count": 0,
        "updated_count": 0,
        "total_found": 0,
        "appeal_synced": 0,
        "error": "",
    }

    try:
        from network_check import check_pcc_network

        net = check_pcc_network()
        if not net["ok"]:
            raise ConnectionError(
                f"{net['message']}。{net.get('detail', '')} "
                "請先用「python scripts/cli.py check-network」診斷。"
            )

        logger.info(f"[{scrape_type}] 開始執行公開招標爬蟲...")
        driver = _create_driver()

        start_date, end_date = _get_bidding_date_range(custom_start_date, custom_end_date)
        logger.info(
            f"公開招標日期區間: {start_date} ~ {end_date}（回溯 {config.BIDDING_LOOKBACK_DAYS} 天）"
        )

        all_raw: list[dict] = []
        for attempt in range(config.MAX_RETRIES):
            try:
                search_url = _build_bidding_search_url(start_date, end_date)
                logger.info(f"[嘗試 {attempt + 1}] 訪問公開招標搜尋頁...")
                driver.get(search_url)
                WebDriverWait(driver, 20).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                _random_delay(3, 6)

                page_source = driver.page_source
                if "查無資料" in page_source or "沒有資料" in page_source:
                    logger.info("查無資料，區間內無公開招標案件")
                    break

                page_tenders = _parse_bidding_table_rows(page_source)
                all_raw.extend(page_tenders)
                logger.info(f"第 1 頁：取得 {len(page_tenders)} 筆")

                page_num = 1
                while True:
                    try:
                        next_links = driver.find_elements(
                            By.XPATH,
                            "//a[contains(text(), '下一頁') or contains(@title, '下一頁')]",
                        )
                        if not next_links:
                            page_num += 1
                            page_links = driver.find_elements(
                                By.XPATH,
                                f"//a[contains(@href, 'pageIndex={page_num}') or text()='{page_num}']",
                            )
                            if not page_links:
                                break
                            next_links = page_links

                        driver.execute_script("arguments[0].click();", next_links[0])
                        _random_delay()
                        WebDriverWait(driver, 15).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )
                        page_source = driver.page_source
                        page_tenders = _parse_bidding_table_rows(page_source)
                        if not page_tenders:
                            break
                        all_raw.extend(page_tenders)
                        logger.info(f"第 {page_num} 頁：取得 {len(page_tenders)} 筆")
                    except (TimeoutException, StaleElementReferenceException):
                        break
                break

            except TimeoutException:
                if attempt < config.MAX_RETRIES - 1:
                    _random_delay(5, 10)
                    continue
                raise
            except WebDriverException as e:
                if attempt < config.MAX_RETRIES - 1:
                    _random_delay(5, 10)
                    if driver:
                        try:
                            driver.quit()
                        except Exception:
                            pass
                    driver = _create_driver()
                    continue
                raise

        all_raw = _dedupe_tenders(all_raw)
        logger.info(f"去重後共 {len(all_raw)} 筆")

        if config.BIDDING_PROC_CATEGORIES:
            proc_filtered = [
                t for t in all_raw
                if _matches_proc_category(t, config.BIDDING_PROC_CATEGORIES)
            ]
            logger.info(
                f"採購性質篩選 {config.BIDDING_PROC_CATEGORIES}："
                f"{len(all_raw)} → {len(proc_filtered)} 筆"
            )
            all_raw = proc_filtered

        if use_filter and config.FILTER_KEYWORDS:
            filtered = [t for t in all_raw if _matches_keywords(t, config.FILTER_KEYWORDS)]
            logger.info(f"關鍵字篩選：{len(all_raw)} → {len(filtered)} 筆")
        else:
            filtered = all_raw

        result["total_found"] = len(filtered)
        new_for_discord: list[dict] = []
        scraped_now = now_tw()

        for tender_data in filtered:
            tid = tender_data.get("tender_id", "").strip()
            if not tid:
                continue

            if _needs_detail_enrichment(tender_data):
                _enrich_bidding_from_detail(driver, tender_data)

            if _sync_appeal_tender(db, tender_data, scraped_now):
                result["appeal_synced"] += 1

            is_new, was_updated = _upsert_bidding_row(db, tender_data, scraped_now)
            if is_new:
                tender_data["scraped_at"] = format_tw(scraped_now)
                tender_data["scraped_at_iso"] = discord_timestamp(scraped_now)
                new_for_discord.append(tender_data)
            elif was_updated:
                result["updated_count"] += 1

        db.commit()
        result["new_count"] = len(new_for_discord)
        result["success"] = True

        logger.info(
            f"[{scrape_type}] 公開招標完成 — 找到 {result['total_found']} 筆, "
            f"新增 {result['new_count']} 筆, 更新 {result['updated_count']} 筆, "
            f"同步徵求表 {result['appeal_synced']} 筆"
        )

        if new_for_discord:
            send_new_bidding_notification(new_for_discord)

        log.finished_at = datetime.now()
        log.total_found = result["total_found"]
        log.new_count = result["new_count"]
        log.updated_count = result["updated_count"]
        log.status = "success"
        db.commit()

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{scrape_type}] 公開招標爬蟲失敗: {error_msg}", exc_info=True)
        result["error"] = error_msg
        log.finished_at = datetime.now()
        log.status = "error"
        log.error_message = error_msg[:2000]
        db.commit()
        send_bidding_error_notification(f"爬蟲類型: {scrape_type}\n錯誤: {error_msg}")

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        db.close()

    return result


def enrich_bidding_contacts(limit: int = None) -> dict:
    """為 bidding_tenders 補抓或修正承辦人/電話"""
    db = SessionLocal()
    driver = None
    result = {
        "success": False,
        "enriched": 0,
        "skipped": 0,
        "failed": 0,
        "no_url": 0,
        "error": "",
    }

    try:
        tenders = db.query(BiddingTender).all()
        targets = [t for t in tenders if _needs_detail_enrichment(t.to_dict())]
        if limit:
            targets = targets[:limit]

        if not targets:
            logger.info("沒有需要補抓的公開招標案件")
            result["success"] = True
            return result

        logger.info(f"開始補抓 {len(targets)} 筆公開招標聯絡資料...")
        driver = _create_driver()

        for tender in targets:
            if not tender.tender_url:
                result["no_url"] += 1
                continue
            data = tender.to_dict()
            try:
                _enrich_bidding_from_detail(driver, data)
                changed = False
                for field in ["tender_name", "contact_person", "phone", "budget", "org_name"]:
                    val = data.get(field, "").strip()
                    if field == "phone" and val:
                        val = _sanitize_phone_for_storage(val)
                    if val and getattr(tender, field, "") != val:
                        setattr(tender, field, val)
                        changed = True
                if changed:
                    tender.updated_at = datetime.now()
                    result["enriched"] += 1
                    logger.info(
                        f"已補抓 {tender.tender_id}: "
                        f"{tender.contact_person} / {tender.phone}"
                    )
                else:
                    result["skipped"] += 1
            except Exception as e:
                result["failed"] += 1
                logger.warning(f"補抓失敗 [{tender.tender_id}]: {e}")

        db.commit()
        result["success"] = True
        logger.info(
            f"公開招標補抓完成 — 成功 {result['enriched']}, "
            f"略過 {result['skipped']}, 無連結 {result['no_url']}, 失敗 {result['failed']}"
        )
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"公開招標補抓失敗: {e}", exc_info=True)
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        db.close()

    return result
