"""
爬蟲核心模組
使用 Selenium 自動化擷取政府電子採購網「公開徵求」公告
"""

import logging
import random
import re
import time
from datetime import datetime, date
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
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(60)
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
        if "案號" in h_clean:
            col_map["tender_id"] = i
        elif "案名" in h_clean or "標案名稱" in h_clean:
            col_map["tender_name"] = i
        elif "機關" in h_clean:
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

                # 擷取連結
                if field in ("tender_name", "tender_id"):
                    link = cell.find("a")
                    if link and link.get("href"):
                        href = link["href"]
                        if not href.startswith("http"):
                            href = config.PCC_BASE_URL + href
                        tender["tender_url"] = href

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
        # 建立 WebDriver
        logger.info(f"[{scrape_type}] 開始執行爬蟲...")
        driver = _create_driver()

        # 設定日期
        today = date.today()
        if custom_start_date and custom_end_date:
            start_date = custom_start_date
            end_date = custom_end_date
        else:
            start_date = today.strftime("%Y/%m/%d")
            end_date = today.strftime("%Y/%m/%d")

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

        # 關鍵字篩選
        if use_filter and config.FILTER_KEYWORDS:
            filtered = [t for t in all_tenders_raw if _matches_keywords(t, config.FILTER_KEYWORDS)]
            logger.info(f"關鍵字篩選：{len(all_tenders_raw)} → {len(filtered)} 筆")
        else:
            filtered = all_tenders_raw

        result["total_found"] = len(filtered)

        # 寫入資料庫（去重）
        new_tenders = []
        updated_tenders = 0
        for tender_data in filtered:
            tid = tender_data.get("tender_id", "").strip()
            if not tid:
                continue

            existing = db.query(Tender).filter_by(tender_id=tid).first()
            if existing:
                # 更新已有記錄（如果狀態有變）
                changed = False
                for field in ["tender_name", "org_name", "contact_person", "phone", "budget", "tender_url"]:
                    new_val = tender_data.get(field, "").strip()
                    if new_val and new_val != getattr(existing, field, ""):
                        setattr(existing, field, new_val)
                        changed = True
                if changed:
                    existing.updated_at = datetime.now()
                    updated_tenders += 1
            else:
                # 新案件
                new_tender = Tender(
                    tender_id=tid,
                    tender_name=tender_data.get("tender_name", "").strip(),
                    org_name=tender_data.get("org_name", "").strip(),
                    contact_person=tender_data.get("contact_person", "").strip(),
                    phone=tender_data.get("phone", "").strip(),
                    budget=tender_data.get("budget", "").strip(),
                    tender_url=tender_data.get("tender_url", "").strip(),
                    status="公開徵求",
                    scraped_at=datetime.now(),
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
                db.add(new_tender)
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

                # 在詳細頁面尋找狀態資訊
                status_text = ""
                for text_elem in soup.find_all(string=re.compile(r"(已決標|公開徵求|已截止|廢標|流標|已公告)")):
                    status_text = text_elem.strip()
                    break

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
