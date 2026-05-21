from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from models import SessionLocal, SalesInsight, Tender, BiddingTender
from device_matcher import match_devices, calculate_vpn_requirements
from pricing_engine import calculate_bid_price
import json

router = APIRouter()

class MatchRequest(BaseModel):
    estimated_users: Optional[int] = 50
    budget: Optional[float] = None

class PriceCalculateRequest(BaseModel):
    margin_rate: Optional[float] = 0.15

@router.get("/api/insights/{tender_id}")
async def get_insight(tender_id: str):
    """取得特定案件的業務洞察資料"""
    db = SessionLocal()
    try:
        insight = db.query(SalesInsight).filter_by(tender_id=tender_id).first()
        if not insight:
            return {"success": False, "message": "尚未建立洞察資料"}
        return {"success": True, "insight": insight.to_dict()}
    finally:
        db.close()

@router.post("/api/insights/{tender_id}/match-device")
async def manual_match_device(tender_id: str, data: MatchRequest):
    """手動觸發設備匹配"""
    db = SessionLocal()
    try:
        insight = db.query(SalesInsight).filter_by(tender_id=tender_id).first()
        
        # 若無 insight 紀錄則自動建立
        if not insight:
            # 必須確認案件存在
            tender = db.query(Tender).filter_by(tender_id=tender_id).first()
            bidding = None
            if not tender:
                bidding = db.query(BiddingTender).filter_by(tender_id=tender_id).first()
                if not bidding:
                    raise HTTPException(status_code=404, detail="找不到該案件號")
                    
            source_table = 'tenders' if tender else 'bidding_tenders'
            org_name = tender.org_name if tender else bidding.org_name
            insight = SalesInsight(tender_id=tender_id, source_table=source_table, org_name=org_name)
            db.add(insight)
            db.commit()

        users = data.estimated_users if data.estimated_users and data.estimated_users > 0 else 50
        
        concurrent_vpn, bandwidth = calculate_vpn_requirements(users)
        devices_json, reason = match_devices(users, data.budget)
        
        insight.estimated_users = users
        insight.vpn_bandwidth_mbps = bandwidth
        insight.recommended_devices_json = devices_json
        insight.device_match_reason = reason
        insight.device_matched_at = __import__('datetime').datetime.now()
        
        db.commit()
        
        return {
            "success": True, 
            "message": "設備匹配完成", 
            "reason": reason,
            "insight": insight.to_dict()
        }
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)
    finally:
        db.close()

@router.post("/api/insights/{tender_id}/calculate-price")
async def manual_calculate_price(tender_id: str, data: PriceCalculateRequest):
    """手動觸發報價計算"""
    db = SessionLocal()
    try:
        insight = db.query(SalesInsight).filter_by(tender_id=tender_id).first()
        if not insight:
            return JSONResponse({"success": False, "message": "找不到該案件的業務洞察，請先執行設備匹配"}, status_code=404)
            
        if not insight.recommended_devices_json or insight.recommended_devices_json == "[]":
            return JSONResponse({"success": False, "message": "無推薦設備，無法計算報價"}, status_code=400)
            
        devices = json.loads(insight.recommended_devices_json)
        primary_device = devices[0] # 取第一台（最推薦的）
        
        # 由於 devices 表內存有 cost_price，我們需要再查一次
        from models import Device
        device = db.query(Device).filter_by(id=primary_device["id"]).first()
        if not device or device.cost_price <= 0:
             return JSONResponse({"success": False, "message": "主推設備無成本價資料，無法計算"}, status_code=400)
             
        suggested_price = calculate_bid_price(device.cost_price, data.margin_rate)
        
        insight.market_price = device.reference_price
        insight.suggested_bid_price = suggested_price
        insight.margin_rate = data.margin_rate
        insight.price_source = f"{device.brand} {device.model} 成本推算"
        insight.price_updated_at = __import__('datetime').datetime.now()
        
        db.commit()
        
        return {
            "success": True,
            "message": "報價計算完成",
            "suggested_bid_price": suggested_price,
            "margin_rate": data.margin_rate,
            "insight": insight.to_dict()
        }
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)
    finally:
        db.close()
