"""
行動外勤管理路由模組
提供外勤戰術面板視圖、LBS 距離計算排序、語音備註與地圖定位 API
"""

import math
import logging
import urllib.request
import urllib.parse
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import text

from models import SessionLocal, OrgContact, ContactLog, SalesInsight, Tender, BiddingTender

logger = logging.getLogger(__name__)
router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# === Pydantic Schema ===
class ContactLogCreate(BaseModel):
    content_text: str
    voice_url: Optional[str] = ""


class GPSUpdateRequest(BaseModel):
    latitude: float
    longitude: float


# === 核心工具函式 ===

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """使用 Haversine 公式計算地球兩點間距離 (公里)"""
    if None in (lat1, lon1, lat2, lon2):
        return float('inf')
    try:
        R = 6371.0  # 地球半徑 (km)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
    except Exception as e:
        logger.error(f"距離計算出錯: {e}")
        return float('inf')


def geocode_address(address: str) -> tuple[Optional[float], Optional[float]]:
    """
    透過 OpenStreetMap Nominatim 免費解析台灣地址經緯度。
    加強 Header 與連線處理，並在失敗時回傳 None。
    """
    if not address or len(address.strip()) < 5:
        return None, None
    
    # 確保地址包含「台灣」或「Taiwan」以防 Nominatim 搞錯國家
    query_addr = address
    if "台灣" not in address and "台北" not in address and "新北" not in address and "台中" not in address and "台南" not in address and "高雄" not in address:
        query_addr = "台灣 " + address

    try:
        url = "https://nominatim.openstreetmap.org/search?q=" + urllib.parse.quote(query_addr) + "&format=json&limit=1"
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'GovProcurementCrawlerMobileSales/1.0 (B2B Procurement platform agent)',
                'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8'
            }
        )
        # 設定 5 秒 timeout 以防阻塞
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data and len(data) > 0:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                logger.info(f"地址 [{address}] 解析成功: {lat}, {lon}")
                return lat, lon
    except Exception as e:
        logger.warning(f"地址 [{address}] 自動解析經緯度失敗: {e}")
    
    return None, None


# === Web 視圖路由 ===

@app_get_route := router.get("/mobile_sales")
async def mobile_sales_page(request: Request):
    """專為行動端最佳化的外勤戰術面板網頁"""
    db = SessionLocal()
    try:
        # 統計追蹤中的高潛力標案數，用來顯示 Badge
        tracked_count = db.query(OrgContact).count()
        return templates.TemplateResponse("mobile_sales.html", {
            "request": request,
            "active_page": "mobile_sales",
            "tracked_count": tracked_count
        })
    finally:
        db.close()


# === API 路由 ===

@router.get("/api/mobile/contacts/radar")
async def list_radar_contacts(
    lat: Optional[float] = Query(None, description="目前 GPS 緯度"),
    lng: Optional[float] = Query(None, description="目前 GPS 經度")
):
    """
    獲取所有聯絡機關/聯絡人，若有提供 lat 與 lng，則計算兩點距離並依距離排序。
    若聯絡人尚未有經緯度，則自動解析並更新至資料庫中。
    """
    db = SessionLocal()
    try:
        contacts = db.query(OrgContact).filter(OrgContact.is_active == True).all()
        updated_any = False
        
        result_list = []
        for c in contacts:
            c_lat = c.latitude
            c_lng = c.longitude
            
            # 若無經緯度且有地址，進行自動解析 (Geocoding)
            if (c_lat is None or c_lng is None) and c.address:
                try:
                    parsed_lat, parsed_lng = geocode_address(c.address)
                    if parsed_lat and parsed_lng:
                        c.latitude = parsed_lat
                        c.longitude = parsed_lng
                        c_lat = parsed_lat
                        c_lng = parsed_lng
                        db.add(c)
                        updated_any = True
                except Exception as ex:
                    logger.error(f"自動背景解析機關地址失敗 {c.org_name}: {ex}")

            # 建立回應字典
            c_dict = c.to_dict()
            
            # 關聯標案資訊與建議設備，便於地圖及列表直接渲染
            insight = None
            if c.source_tender_id:
                insight = db.query(SalesInsight).filter_by(tender_id=c.source_tender_id).first()
            
            if insight:
                c_dict["insight"] = insight.to_dict()
                # 附帶最推薦的主推型號
                try:
                    devices = json.loads(insight.recommended_devices_json)
                    if devices and len(devices) > 0:
                        c_dict["primary_device"] = f"{devices[0].get('brand', '')} {devices[0].get('model', '')}"
                        c_dict["device_cost"] = devices[0].get('cost_price', 0)
                        c_dict["device_market"] = devices[0].get('reference_price', 0)
                    else:
                        c_dict["primary_device"] = "—"
                except:
                    c_dict["primary_device"] = "—"
            else:
                c_dict["insight"] = None
                c_dict["primary_device"] = "—"

            # 計算距離
            if lat is not None and lng is not None and c_lat is not None and c_lng is not None:
                distance = calculate_distance(lat, lng, c_lat, c_lng)
                c_dict["distance_km"] = round(distance, 2)
            else:
                c_dict["distance_km"] = None

            result_list.append(c_dict)

        if updated_any:
            db.commit()

        # 排序：若有 GPS 資訊，優先將距離近的排前面；其餘無經緯度或無法計算的排後面
        if lat is not None and lng is not None:
            result_list.sort(key=lambda x: (x["distance_km"] is None, x["distance_km"] or float('inf')))
        else:
            result_list.sort(key=lambda x: x["org_name"])

        return {"success": True, "contacts": result_list}
    except Exception as e:
        logger.error(f"取得雷達列表失敗: {e}", exc_info=True)
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)
    finally:
        db.close()


@router.post("/api/mobile/contacts/{contact_id}/log")
async def add_interaction_log(contact_id: int, data: ContactLogCreate):
    """寫入業務互動紀錄，包含 HTML5 Web Speech 轉換的繁體文字或手動手寫文字"""
    db = SessionLocal()
    try:
        contact = db.query(OrgContact).filter_by(id=contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail="找不到該聯絡人")

        new_log = ContactLog(
            contact_id=contact_id,
            content_text=data.content_text,
            voice_url=data.voice_url
        )
        db.add(new_log)
        
        # 同步更新主表的更新時間與 notes 備註（追加）
        contact.updated_at = datetime.now()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        append_note = f"[{timestamp} 訪問] {data.content_text}"
        if contact.notes:
            contact.notes = f"{contact.notes}\n{append_note}"
        else:
            contact.notes = append_note
            
        db.commit()
        return {"success": True, "message": "訪問紀錄已成功保存！", "log": new_log.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"寫入訪問紀錄失敗: {e}")
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)
    finally:
        db.close()


@router.post("/api/mobile/contacts/{contact_id}/geocode")
async def trigger_manual_geocode(contact_id: int):
    """手動對特定聯絡人進行地址重新定位解析"""
    db = SessionLocal()
    try:
        contact = db.query(OrgContact).filter_by(id=contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail="找不到該聯絡人")
            
        if not contact.address:
            return JSONResponse({"success": False, "message": "該聯絡人尚未登錄地址，無法解析定位"}, status_code=400)
            
        lat, lon = geocode_address(contact.address)
        if lat and lon:
            contact.latitude = lat
            contact.longitude = lon
            contact.updated_at = datetime.now()
            db.commit()
            return {"success": True, "message": "地址定位解析成功！", "latitude": lat, "longitude": lon}
        else:
            return JSONResponse({"success": False, "message": "開源地址定位服務解析失敗，請手動設定座標"}, status_code=400)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"手動定位解析失敗: {e}")
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)
    finally:
        db.close()


@router.post("/api/mobile/contacts/{contact_id}/update-gps")
async def update_contact_gps(contact_id: int, data: GPSUpdateRequest):
    """地圖拖曳或人工手動精準修改聯絡人/機關 GPS 定位座標"""
    db = SessionLocal()
    try:
        contact = db.query(OrgContact).filter_by(id=contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail="找不到該聯絡人")
            
        contact.latitude = data.latitude
        contact.longitude = data.longitude
        contact.updated_at = datetime.now()
        
        db.commit()
        return {"success": True, "message": "GPS 座標已更新！", "latitude": data.latitude, "longitude": data.longitude}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新 GPS 座標失敗: {e}")
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)
    finally:
        db.close()
