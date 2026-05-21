"""
模組 A：104 人力銀行遠端工作探測器
爬取 104 企業職缺，分析遠端工作潛力並為客戶評分。
"""

import logging
import urllib.parse
from datetime import datetime
import json
import time

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from config import config
from models import SessionLocal, SalesInsight, AnalysisLog
from scraper import _create_driver, _random_delay
from time_utils import now_tw

logger = logging.getLogger(__name__)

# 關鍵字定義
REMOTE_KEYWORDS = ["遠端", "居家", "wfh", "remote", "work from home", "遠距"]
NETADMIN_KEYWORDS = ["網管", "mis", "資訊", "網路", "系統", "it", "工程師", "資安"]


def _should_skip_org(org_name: str) -> str:
    """檢查是否符合略過條件"""
    if not org_name:
        return "機關名稱空白"
    for kw in config.JOB104_SKIP_KEYWORDS:
        if kw in org_name:
            return f"包含略過關鍵字: {kw}"
    return ""


def _search_104_jobs(driver, keyword: str) -> list[dict]:
    """搜尋 104 職缺並回傳簡要資訊"""
    # 104 搜尋 URL 編碼
    encoded_kw = urllib.parse.quote(keyword)
    url = f"https://www.104.com.tw/jobs/search/?ro=0&kwop=7&keyword={encoded_kw}&expansionType=area%2Cspec%2Ccom%2Cjob%2Cwf%2Cwktm&order=15&asc=0&page=1&mode=s&jobsource=2018indexpoc&langFlag=0&langStatus=0&recommendJob=1&hotJob=1"
    
    jobs = []
    try:
        driver.get(url)
        _random_delay(2, 4)
        
        # 等待職缺列表載入
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "js-job-content"))
        )
        
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")
        
        # 尋找所有職缺卡片
        job_articles = soup.find_all("article", class_="job-list-item")
        
        for article in job_articles:
            # 排除廣告或非正常職缺
            if "job-list-item--advertiser" in article.get("class", []):
                continue
                
            job_title_elem = article.find("a", class_="js-job-link")
            comp_name_elem = article.find("a", class_="gtm-list-comp")
            desc_elem = article.find("p", class_="job-list-item__info")
            
            if not job_title_elem:
                continue
                
            job_title = job_title_elem.get_text(strip=True)
            job_link = job_title_elem.get("href", "")
            if job_link.startswith("//"):
                job_link = "https:" + job_link
                
            comp_name = comp_name_elem.get_text(strip=True) if comp_name_elem else ""
            desc = desc_elem.get_text(strip=True) if desc_elem else ""
            
            # 簡易檢查公司名稱是否包含搜尋關鍵字（避免搜到完全無關的）
            # 注意：政府機關有時候公司名稱會不一樣，這裡放寬一點
            
            jobs.append({
                "title": job_title,
                "company": comp_name,
                "description": desc,
                "link": job_link
            })
            
            # 只取前 10 筆就夠分析了
            if len(jobs) >= 10:
                break
                
    except TimeoutException:
        logger.warning(f"[104] 搜尋超時: {keyword}")
    except Exception as e:
        logger.error(f"[104] 搜尋異常 {keyword}: {e}")
        
    return jobs


def _analyze_jobs(jobs: list[dict]) -> tuple[int, int, int, list[dict]]:
    """分析職缺內容，回傳 (分數, 遠端數, 網管數, 詳情)"""
    score = 0
    remote_count = 0
    netadmin_count = 0
    details = []
    
    if not jobs:
        return 0, 0, 0, []
        
    for job in jobs:
        title_lower = job["title"].lower()
        desc_lower = job["description"].lower()
        content = title_lower + " " + desc_lower
        
        is_remote = any(kw in content for kw in REMOTE_KEYWORDS)
        is_netadmin = any(kw in content for kw in NETADMIN_KEYWORDS)
        
        job_score = 0
        if is_remote:
            job_score += 50
            remote_count += 1
        if is_netadmin:
            job_score += 10
            netadmin_count += 1
            
        if is_remote and is_netadmin:
            job_score += 40  # 網管又可遠端，超級目標客戶
            
        score += job_score
        details.append({
            "title": job["title"],
            "is_remote": is_remote,
            "is_netadmin": is_netadmin,
            "score": job_score
        })
        
    # 分數正規化到 0~100
    final_score = min(100, score)
    return final_score, remote_count, netadmin_count, details


def analyze_single_tender(db, insight: SalesInsight, driver=None) -> dict:
    """分析單一案件（模組 A）"""
    close_driver = False
    if not driver:
        driver = _create_driver()
        close_driver = True
        
    log = AnalysisLog(
        tender_id=insight.tender_id,
        module="job104",
        status="running",
        started_at=datetime.now(),
    )
    db.add(log)
    db.commit()
    
    result = {
        "success": False,
        "score": 0,
        "status": "error",
        "message": ""
    }
    
    try:
        # 1. 檢查是否略過
        skip_reason = _should_skip_org(insight.org_name)
        if skip_reason:
            insight.skip_reason = skip_reason
            insight.job_analyzed_at = datetime.now()
            
            log.status = "skipped"
            log.message = skip_reason
            log.finished_at = datetime.now()
            db.commit()
            
            result["status"] = "skipped"
            result["message"] = skip_reason
            result["success"] = True
            return result
            
        # 2. 搜尋 104
        search_kw = insight.org_name
        # 嘗試去除「機關」、「局」等後綴以提高命中率，但先直接搜
        jobs = _search_104_jobs(driver, search_kw)
        
        # 若機關名稱搜不到，若有統編則改搜統編
        if not jobs and insight.org_tax_id:
            logger.info(f"[{insight.tender_id}] 標案單位搜無職缺，改搜統編: {insight.org_tax_id}")
            jobs = _search_104_jobs(driver, insight.org_tax_id)
            
        # 3. 分析結果
        score, remote_cnt, netadmin_cnt, details = _analyze_jobs(jobs)
        
        insight.remote_score = score
        insight.remote_job_count = remote_cnt
        insight.netadmin_job_count = netadmin_cnt
        insight.total_job_count = len(jobs)
        insight.job_analysis_json = json.dumps(details, ensure_ascii=False)
        insight.job_analyzed_at = datetime.now()
        
        log.status = "success"
        log.message = f"找到 {len(jobs)} 職缺, 分數: {score}"
        log.finished_at = datetime.now()
        db.commit()
        
        result["success"] = True
        result["status"] = "success"
        result["score"] = score
        result["message"] = log.message
        
        # 若分數大於 50，可觸發高潛力通知
        if score >= 50:
            try:
                from discord_notifier import send_high_potential_notification
                # 需要取得 tender 資訊
                from models import Tender, BiddingTender
                tender_data = {}
                if insight.source_table == "tenders":
                    t = db.query(Tender).filter_by(tender_id=insight.tender_id).first()
                    if t: tender_data = t.to_dict()
                else:
                    t = db.query(BiddingTender).filter_by(tender_id=insight.tender_id).first()
                    if t: tender_data = t.to_dict()
                    
                if tender_data:
                    send_high_potential_notification(tender_data, insight.to_dict())
            except Exception as e:
                logger.error(f"發送高潛力通知失敗: {e}")
                
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[104分析] 失敗 {insight.tender_id}: {error_msg}")
        log.status = "error"
        log.message = error_msg[:2000]
        log.finished_at = datetime.now()
        db.commit()
        result["message"] = error_msg
    finally:
        if close_driver and driver:
            try:
                driver.quit()
            except:
                pass
                
    return result


def run_batch_analysis(limit: int = 20) -> dict:
    """批次執行未分析過的案件"""
    db = SessionLocal()
    driver = None
    
    result = {
        "success": False,
        "total": 0,
        "processed": 0,
        "skipped": 0,
        "errors": 0,
    }
    
    try:
        # 找還沒分析過且沒有 skip_reason 的
        insights = db.query(SalesInsight).filter(
            SalesInsight.job_analyzed_at.is_(None),
            SalesInsight.skip_reason == ""
        ).limit(limit).all()
        
        result["total"] = len(insights)
        if not insights:
            result["success"] = True
            return result
            
        driver = _create_driver()
        
        for insight in insights:
            res = analyze_single_tender(db, insight, driver)
            if res["status"] == "skipped":
                result["skipped"] += 1
            elif res["success"]:
                result["processed"] += 1
            else:
                result["errors"] += 1
                
            _random_delay(2, 5)
            
        result["success"] = True
        logger.info(f"[104批次分析] 處理: {result['processed']}, 略過: {result['skipped']}, 錯誤: {result['errors']}")
        
    except Exception as e:
        logger.error(f"[104批次分析] 發生錯誤: {e}", exc_info=True)
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        db.close()
        
    return result
