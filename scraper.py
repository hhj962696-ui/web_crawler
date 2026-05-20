"""
爬蟲核心模組
使用 Selenium 自動化擷取政府電子採購網「公開徵求」公告
"""

import logging
import os
import random
import re
import sys
import time
from datetime import datetime, date, timedelta

from time_utils import now_tw, format_tw, discord_timestamp
from typing import Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    WebDriverException, StaleElementReferenceException
)
from webdriver_manager.chrome import ChromeDriverManager

from config import config
from models import SessionLocal, Tender, ScrapeLog
from discord_notifier import (
    send_new_tenders_notification,
    send_status_change_notification,
    send_error_notification,
)

logger = logging.getLogger(__name__)

# 追蹤狀態偵測優先序（先匹配較終態的狀態）
TRACKED_STATUS_KEYWORDS = (
    "已決標", "廢標", "流標", "已截止", "公開徵求", "已公告",
)

DETAIL_FIELD_LABELS = {
    "tender_name": ("標案名稱",),
    "contact_person": ("承辦人", "聯絡人", "聯絡窗口", "採購人"),
    "phone": ("電話", "聯絡電話", "聯絡電話號碼", "分機"),
    "budget": ("預算金額", "預算", "採購金額", "契約金額", "公告金額"),
    "org_name": ("招標機關", "機關名稱", "採購機關"),
}

DETAIL_URL_MARKERS = ("urlSelector/common/tpAppeal", "readTpAppeal")


def _create_driver() -> webdriver.Chrome:
    """建立 Chrome WebDriver 實例"""
    chrome_options = Options()

    if config.CHROME_HEADLESS:
        chrome_options.add_argument("--headless=new")

    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    chrome_options.add_experimental_option(
        "excludeSwitches", ["enable-automation", "enable-logging"]
    )
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--ignore-certificate-errors")

    proxy = config.HTTPS_PROXY or config.HTTP_PROXY
    if proxy:
        chrome_options.add_argument(f"--proxy-server={proxy}")
        logger.info(f"使用 Proxy: {proxy}")

    if config.CHROMIUM_BIN:
        chrome_options.binary_location = config.CHROMIUM_BIN

    log_path = "NUL" if sys.platform == "win32" else os.devnull
    if config.CHROMEDRIVER_PATH:
        service = Service(config.CHROMEDRIVER_PATH, log_output=log_path)
    else:
        service = Service(ChromeDriverManager().install(), log_output=log_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
    driver.implicitly_wait(10)
    return driver


def _random_delay(min_sec: float = None, max_sec: float = None):
    """隨機延遲"""
    mn = min_sec or config.REQUEST_DELAY_MIN
    mx = max_sec or config.REQUEST_DELAY_MAX
    delay = random.uniform(mn, mx)
    time.sleep(delay)


def _build_search_url(start_date: str, end_date: str) -> str:
    """建構搜尋 URL"""
    params = {
        "firstSearch": "true",
        "searchType": "basic",
        "isBinding": "N",
        "isLogIn": "N",
        "orgName": "",
        "orgId": "",
        "tenderName": "",
        "tenderId": "",
        "tenderType": "SEARCH_APPEAL",
        "dateType": "isNow",
        "startDate": start_date,
        "endDate": end_date,
        "radProctrgCate": "",
        "policyAdvocacy": "",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{config.PCC_SEARCH_URL}?{query}"


def _get_scrape_date_range(
    custom_start_date: str = None,
    custom_end_date: str = None,
) -> tuple[str, str]:
    """取得爬蟲日期區間（YYYY/MM/DD）"""
    today = date.today()
    if custom_start_date and custom_end_date:
        return custom_start_date, custom_end_date

    lookback = config.SCRAPE_LOOKBACK_DAYS
    start = today - timedelta(days=lookback - 1)
    return start.strftime("%Y/%m/%d"), today.strftime("%Y/%m/%d")


def _dedupe_tenders(tenders: list[dict]) -> list[dict]:
    """以案號去重，保留資訊較完整的版本"""
    by_id: dict[str, dict] = {}
    no_id: list[dict] = []

    for tender in tenders:
        tid = tender.get("tender_id", "").strip()
        if not tid:
            no_id.append(tender)
            continue

        existing = by_id.get(tid)
        if not existing:
            by_id[tid] = tender
            continue

        for field in ("tender_name", "org_name", "contact_person", "phone", "budget", "tender_url"):
            if not existing.get(field) and tender.get(field):
                existing[field] = tender[field]

    return list(by_id.values()) + no_id


def _needs_detail_enrichment(tender: dict) -> bool:
    """列表頁欄位不足時進詳情頁補抓"""
    return not all(
        tender.get(f, "").strip()
        for f in ("contact_person", "phone", "budget")
    )


def _label_matches(label: str, keywords: tuple[str, ...]) -> bool:
    return any(kw in label for kw in keywords)


def _assign_detail_field(parsed: dict[str, str], field: str, value: str):
    """寫入詳情欄位（保留較長/較完整的值）"""
    value = (value or "").strip()
    if not value or value in ("-", "無", "N/A"):
        return
    if field not in parsed or len(value) > len(parsed.get(field, "")):
        parsed[field] = value


def _parse_label_value_pairs(soup: BeautifulSoup) -> dict[str, str]:
    """從詳情頁表格 label/value 配對解析欄位（支援 td+td、th+td）"""
    parsed: dict[str, str] = {}

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue

            # 標準兩欄列：標籤 | 值
            if len(cells) == 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                for field, labels in DETAIL_FIELD_LABELS.items():
                    if _label_matches(label, labels):
                        _assign_detail_field(parsed, field, value)
                continue

            # 多欄橫向排列：標籤, 值, 標籤, 值, ...
            i = 0
            while i < len(cells) - 1:
                label = cells[i].get_text(strip=True)
                value = cells[i + 1].get_text(strip=True)
                matched = False
                for field, labels in DETAIL_FIELD_LABELS.items():
                    if _label_matches(label, labels):
                        _assign_detail_field(parsed, field, value)
                        matched = True
                        break
                i += 2 if matched else 1

    # 備援：從全文找電話格式
    if "phone" not in parsed:
        page_text = soup.get_text(" ", strip=True)
        phone_match = re.search(
            r"(?:\(0\d{1,2}\)|0\d{1,2}[-－])?\d{6,8}(?:#\d+)?",
            page_text,
        )
        if phone_match:
            parsed["phone"] = phone_match.group(0)

    return parsed


def _normalize_detail_url(href: str) -> str:
    """轉成完整詳情頁 URL"""
    if not href:
        return ""
    href = href.strip()
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"{config.PCC_BASE_URL}{href}"
    return f"{config.PCC_BASE_URL}/{href.lstrip('/')}"


def _extract_detail_url_from_row(row) -> str:
    """從列表列的「檢視」等連結取得公開徵求詳情 URL"""
    for link in row.find_all("a", href=True):
        href = link.get("href", "")
        if any(marker in href for marker in DETAIL_URL_MARKERS):
            return _normalize_detail_url(href)
        title = (link.get("title") or "") + (link.get_text(strip=True) or "")
        if "檢視" in title or "view" in title.lower():
            return _normalize_detail_url(href)
    return ""


def _extract_status_from_soup(soup: BeautifulSoup) -> str:
    """從詳情頁擷取案件狀態（依優先序）"""
    page_text = soup.get_text(" ", strip=True)
    for keyword in TRACKED_STATUS_KEYWORDS:
        if keyword in page_text:
            return keyword
    return ""


def _parse_detail_page(page_source: str) -> dict:
    """解析詳情頁補充欄位與狀態"""
    soup = BeautifulSoup(page_source, "html.parser")
    fields = _parse_label_value_pairs(soup)
    status = _extract_status_from_soup(soup)
    if status:
        fields["status"] = status
    return fields


def _load_detail_page(driver: webdriver.Chrome, url: str) -> str:
    """載入詳情頁並回傳 HTML"""
    driver.get(url)
    _random_delay(2, 4)
    WebDriverWait(driver, 15).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    return driver.page_source


def _enrich_tender_from_detail(driver: webdriver.Chrome, tender: dict) -> dict:
    """進入詳情頁補齊承辦人、電話、預算等欄位"""
    url = tender.get("tender_url", "").strip()
    if not url:
        return tender

    try:
        page_source = _load_detail_page(driver, url)
        detail = _parse_detail_page(page_source)

        for field in ("tender_name", "contact_person", "phone", "budget", "org_name", "status"):
            value = detail.get(field, "").strip()
            if value and not tender.get(field, "").strip():
                tender[field] = value

        if not tender.get("status"):
            tender["status"] = detail.get("status") or "公開徵求"

        logger.debug(
            f"詳情補抓 [{tender.get('tender_id')}]: "
            f"聯絡={tender.get('contact_person')}, 電話={tender.get('phone')}"
        )

    except Exception as e:
        logger.warning(f"詳情頁補抓失敗 [{tender.get('tender_id')}]: {e}")

    return tender


def _parse_table_rows(page_source: str) -> list[dict]:
    """解析結果頁面 HTML 表格，擷取案件資料"""
    soup = BeautifulSoup(page_source, "html.parser")
    results = []

    # 搜尋結果表格
    table = soup.find("table", class_="tb_01") or soup.find("table", {"id": "tpAppeal"})
    if not table:
        # 嘗試其他可能的表格
        tables = soup.find_all("table")
        for t in tables:
            if t.find("th") and ("案號" in t.get_text() or "案名" in t.get_text()):
                table = t
                break

    if not table:
        logger.warning("找不到結果表格")
        return results

    rows = table.find_all("tr")
    header_row = rows[0] if rows else None

    if not header_row:
        return results

    # 解析表頭取得欄位索引
    headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
    col_map = {}
    for i, h in enumerate(headers):
        h_clean = h.strip()
        if "標案案號" in h_clean or h_clean == "案號" or "案號" in h_clean:
            col_map["tender_id"] = i
        elif "標案名稱" in h_clean or "案名" in h_clean:
            col_map["tender_name"] = i
        elif "機關名稱" in h_clean or ("機關" in h_clean and "代碼" not in h_clean):
            col_map["org_name"] = i
        elif "承辦人" in h_clean or "聯絡人" in h_clean:
            col_map["contact_person"] = i
        elif "電話" in h_clean:
            col_map["phone"] = i
        elif "預算" in h_clean or "金額" in h_clean:
            col_map["budget"] = i

    # 解析資料列
    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        tender = {
            "tender_id": "",
            "tender_name": "",
            "org_name": "",
            "contact_person": "",
            "phone": "",
            "budget": "",
            "tender_url": "",
        }

        for field, idx in col_map.items():
            if idx < len(cells):
                cell = cells[idx]
                tender[field] = cell.get_text(strip=True)

        # 詳情頁連結在「檢視」欄（urlSelector/common/tpAppeal?pk=...）
        detail_url = _extract_detail_url_from_row(row)
        if detail_url:
            tender["tender_url"] = detail_url

        # 如果表格結構不符預期，嘗試按位置解析
        if not tender["tender_id"] and not col_map:
            # 通用解析：嘗試從第一個或第二個 cell 取得資料
            for cell in cells:
                text = cell.get_text(strip=True)
                link = cell.find("a")

                # 看起來像案號的文字
                if re.match(r'^[A-Za-z0-9\-_]+$', text) and len(text) > 5:
                    if not tender["tender_id"]:
                        tender["tender_id"] = text
                        if link and link.get("href"):
                            href = link["href"]
                            if not href.startswith("http"):
                                href = config.PCC_BASE_URL + href
                            tender["tender_url"] = href

        if tender["tender_id"] or tender["tender_name"]:
            results.append(tender)

    return results


def _matches_keywords(tender: dict, keywords: list[str]) -> bool:
    """檢查案件是否匹配篩選關鍵字"""
    if not keywords:
        return True  # 沒有設定關鍵字時，全部通過

    text = f"{tender.get('tender_name', '')} {tender.get('org_name', '')}"
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def run_scraper(
    scrape_type: str = "daily",
    use_filter: bool = True,
    custom_start_date: str = None,
    custom_end_date: str = None,
) -> dict:
    """
    執行爬蟲主流程

    Args:
        scrape_type: 爬蟲類型 (daily/manual/track_check)
        use_filter: 是否使用關鍵字篩選
        custom_start_date: 自訂起始日期 (YYYY/MM/DD)
        custom_end_date: 自訂結束日期 (YYYY/MM/DD)

    Returns:
        dict with keys: success, new_count, total_found, error
    """
    db = SessionLocal()
    log = ScrapeLog(
        started_at=datetime.now(),
        scrape_type=scrape_type,
        status="running",
    )
    db.add(log)
    db.commit()

    driver = None
    result = {"success": False, "new_count": 0, "updated_count": 0, "total_found": 0, "error": ""}

    try:
        from network_check import check_pcc_network

        net = check_pcc_network()
        if not net["ok"]:
            raise ConnectionError(
                f"{net['message']}。{net.get('detail', '')} "
                "請先用「python scripts/cli.py check-network」診斷，"
                "或於瀏覽器手動開啟 https://web.pcc.gov.tw 確認能否連線。"
            )

        # 建立 WebDriver
        logger.info(f"[{scrape_type}] 開始執行爬蟲...")
        driver = _create_driver()

        start_date, end_date = _get_scrape_date_range(custom_start_date, custom_end_date)
        logger.info(f"爬取日期區間: {start_date} ~ {end_date}（回溯 {config.SCRAPE_LOOKBACK_DAYS} 天）")

        # 嘗試重試機制
        all_tenders_raw = []
        for attempt in range(config.MAX_RETRIES):
            try:
                search_url = _build_search_url(start_date, end_date)
                logger.info(f"[嘗試 {attempt + 1}] 訪問搜尋頁面...")
                driver.get(search_url)

                # 等待頁面載入完成
                WebDriverWait(driver, 20).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                _random_delay(3, 6)

                # 檢查是否有結果
                page_source = driver.page_source
                if "查無資料" in page_source or "沒有資料" in page_source:
                    logger.info("查無資料，當日無公開徵求案件")
                    break

                # 解析第一頁
                page_tenders = _parse_table_rows(page_source)
                all_tenders_raw.extend(page_tenders)
                logger.info(f"第 1 頁：取得 {len(page_tenders)} 筆資料")

                # 處理分頁
                page_num = 1
                while True:
                    try:
                        # 尋找「下一頁」按鈕
                        next_links = driver.find_elements(
                            By.XPATH,
                            "//a[contains(text(), '下一頁') or contains(@title, '下一頁')]"
                        )
                        if not next_links:
                            # 嘗試找頁碼連結
                            page_num += 1
                            page_links = driver.find_elements(
                                By.XPATH,
                                f"//a[contains(@href, 'pageIndex={page_num}') or text()='{page_num}']"
                            )
                            if not page_links:
                                break
                            next_links = page_links

                        # 點擊下一頁
                        next_link = next_links[0]
                        driver.execute_script("arguments[0].click();", next_link)
                        _random_delay()

                        # 等待新頁面載入
                        WebDriverWait(driver, 15).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )

                        page_source = driver.page_source
                        page_tenders = _parse_table_rows(page_source)

                        if not page_tenders:
                            break

                        all_tenders_raw.extend(page_tenders)
                        logger.info(f"第 {page_num} 頁：取得 {len(page_tenders)} 筆資料")

                    except (TimeoutException, StaleElementReferenceException):
                        logger.info(f"分頁結束（第 {page_num} 頁）")
                        break

                # 成功取得資料，跳出重試迴圈
                break

            except TimeoutException:
                logger.warning(f"[嘗試 {attempt + 1}] 頁面載入逾時")
                if attempt < config.MAX_RETRIES - 1:
                    _random_delay(5, 10)
                    continue
                raise
            except WebDriverException as e:
                logger.warning(f"[嘗試 {attempt + 1}] WebDriver 錯誤: {e}")
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

        all_tenders_raw = _dedupe_tenders(all_tenders_raw)
        logger.info(f"去重後共 {len(all_tenders_raw)} 筆")

        # 關鍵字篩選
        if use_filter and config.FILTER_KEYWORDS:
            filtered = [t for t in all_tenders_raw if _matches_keywords(t, config.FILTER_KEYWORDS)]
            logger.info(f"關鍵字篩選：{len(all_tenders_raw)} → {len(filtered)} 筆")
        else:
            filtered = all_tenders_raw

        result["total_found"] = len(filtered)

        # 分離新案與既有案
        new_candidates: list[dict] = []
        updated_tenders = 0
        for tender_data in filtered:
            tid = tender_data.get("tender_id", "").strip()
            if not tid:
                continue

            existing = db.query(Tender).filter_by(tender_id=tid).first()
            if existing:
                changed = False
                for field in ["tender_name", "org_name", "contact_person", "phone", "budget", "tender_url"]:
                    new_val = tender_data.get(field, "").strip()
                    if new_val and new_val != getattr(existing, field, ""):
                        setattr(existing, field, new_val)
                        changed = True
                # 既有案缺聯絡資料時，用詳情頁補抓
                if _needs_detail_enrichment(existing.to_dict()):
                    enrich_data = existing.to_dict()
                    enrich_data["tender_url"] = (
                        tender_data.get("tender_url") or existing.tender_url or ""
                    )
                    if enrich_data["tender_url"]:
                        _enrich_tender_from_detail(driver, enrich_data)
                        for field in ["tender_name", "contact_person", "phone", "budget", "org_name"]:
                            val = enrich_data.get(field, "").strip()
                            if val and val != getattr(existing, field, ""):
                                setattr(existing, field, val)
                                changed = True
                if changed:
                    existing.updated_at = datetime.now()
                    updated_tenders += 1
            else:
                tender_data.setdefault("status", "公開徵求")
                new_candidates.append(tender_data)

        # 新案進詳情頁補抓後再入庫
        new_tenders: list[dict] = []
        scraped_now = now_tw()
        for tender_data in new_candidates:
            if _needs_detail_enrichment(tender_data):
                _enrich_tender_from_detail(driver, tender_data)

            tid = tender_data.get("tender_id", "").strip()
            db.add(Tender(
                tender_id=tid,
                tender_name=tender_data.get("tender_name", "").strip(),
                org_name=tender_data.get("org_name", "").strip(),
                contact_person=tender_data.get("contact_person", "").strip(),
                phone=tender_data.get("phone", "").strip(),
                budget=tender_data.get("budget", "").strip(),
                tender_url=tender_data.get("tender_url", "").strip(),
                status=tender_data.get("status", "公開徵求") or "公開徵求",
                scraped_at=scraped_now.replace(tzinfo=None),
                created_at=scraped_now.replace(tzinfo=None),
                updated_at=scraped_now.replace(tzinfo=None),
            ))
            tender_data["scraped_at"] = format_tw(scraped_now)
            tender_data["scraped_at_iso"] = discord_timestamp(scraped_now)
            new_tenders.append(tender_data)

        db.commit()
        result["new_count"] = len(new_tenders)
        result["updated_count"] = updated_tenders
        result["success"] = True

        logger.info(
            f"[{scrape_type}] 爬蟲完成 — "
            f"找到 {result['total_found']} 筆, "
            f"新增 {result['new_count']} 筆, "
            f"更新 {result['updated_count']} 筆"
        )

        # Discord 通知（僅新案件）
        if new_tenders:
            send_new_tenders_notification(new_tenders)

        # 更新日誌
        log.finished_at = datetime.now()
        log.total_found = result["total_found"]
        log.new_count = result["new_count"]
        log.updated_count = result["updated_count"]
        log.status = "success"
        db.commit()

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{scrape_type}] 爬蟲執行失敗: {error_msg}", exc_info=True)
        result["error"] = error_msg
        result["success"] = False

        # 更新日誌
        log.finished_at = datetime.now()
        log.status = "error"
        log.error_message = error_msg[:2000]
        db.commit()

        # Discord 錯誤通知
        send_error_notification(f"爬蟲類型: {scrape_type}\n錯誤: {error_msg}")

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        db.close()

    return result


def enrich_missing_contacts(limit: int = None) -> dict:
    """
    為資料庫中缺少承辦人/電話的既有案件補抓詳情頁。
    需已有 tender_url（請先重新 scrape 以更新連結）。
    """
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
        tenders = db.query(Tender).all()
        targets = [t for t in tenders if _needs_detail_enrichment(t.to_dict())]
        if limit:
            targets = targets[:limit]

        if not targets:
            logger.info("沒有需要補抓聯絡資料的案件")
            result["success"] = True
            return result

        logger.info(f"開始補抓 {len(targets)} 筆案件聯絡資料...")
        driver = _create_driver()

        for tender in targets:
            if not tender.tender_url:
                result["no_url"] += 1
                continue
            data = tender.to_dict()
            try:
                _enrich_tender_from_detail(driver, data)
                changed = False
                for field in ["tender_name", "contact_person", "phone", "budget", "org_name"]:
                    val = data.get(field, "").strip()
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
            f"補抓完成 — 成功 {result['enriched']}, "
            f"略過 {result['skipped']}, 無連結 {result['no_url']}, 失敗 {result['failed']}"
        )

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"補抓聯絡資料失敗: {e}", exc_info=True)

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        db.close()

    return result


def check_tracked_tenders() -> dict:
    """
    檢查被追蹤案件的狀態變化
    重新爬取追蹤案件的詳細頁面，比對狀態
    """
    db = SessionLocal()
    result = {"success": False, "checked": 0, "changed": 0, "error": ""}
    driver = None

    try:
        tracked = db.query(Tender).filter_by(is_tracked=True).all()
        if not tracked:
            logger.info("沒有被追蹤的案件")
            result["success"] = True
            return result

        logger.info(f"開始檢查 {len(tracked)} 個追蹤案件...")
        driver = _create_driver()

        for tender in tracked:
            try:
                if not tender.tender_url:
                    continue

                driver.get(tender.tender_url)
                _random_delay()

                WebDriverWait(driver, 15).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )

                page_source = driver.page_source
                soup = BeautifulSoup(page_source, "html.parser")
                detail = _parse_detail_page(page_source)

                # 順便更新詳情欄位
                for field in ("contact_person", "phone", "budget", "org_name"):
                    value = detail.get(field, "").strip()
                    if value and value != getattr(tender, field, ""):
                        setattr(tender, field, value)

                status_text = detail.get("status") or _extract_status_from_soup(soup)

                if status_text and status_text != tender.status:
                    old_status = tender.status
                    tender.status = status_text
                    tender.updated_at = datetime.now()
                    result["changed"] += 1

                    # 發送狀態變更通知
                    send_status_change_notification(
                        tender.to_dict(), old_status, status_text
                    )
                    logger.info(f"案件 {tender.tender_id} 狀態變更: {old_status} → {status_text}")

                result["checked"] += 1

            except Exception as e:
                logger.warning(f"檢查案件 {tender.tender_id} 時發生錯誤: {e}")
                continue

        db.commit()
        result["success"] = True
        logger.info(f"追蹤檢查完成：檢查 {result['checked']} 筆，{result['changed']} 筆狀態變更")

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"追蹤檢查失敗: {e}", exc_info=True)

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        db.close()

    return result
