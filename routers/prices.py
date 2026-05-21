from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from pricing_engine import record_price, get_price_trend

router = APIRouter()

class PriceRecordRequest(BaseModel):
    device_id: int
    price: float
    price_type: Optional[str] = "market"
    source: Optional[str] = ""
    tender_id: Optional[str] = ""

@router.get("/api/prices/history")
async def api_get_price_history(device_id: int, days: int = 90):
    """取得設備價格歷史趨勢"""
    try:
        history = get_price_trend(device_id, days)
        return {"success": True, "history": history}
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)

@router.post("/api/prices/record")
async def api_record_price(data: PriceRecordRequest):
    """手動記錄市場價/決標價"""
    ok = record_price(
        device_id=data.device_id,
        price=data.price,
        price_type=data.price_type,
        source=data.source,
        tender_id=data.tender_id
    )
    if ok:
        return {"success": True, "message": "價格已記錄"}
    return JSONResponse({"success": False, "message": "記錄失敗，請確認設備ID是否正確"}, status_code=400)
