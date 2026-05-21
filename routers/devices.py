from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

from models import SessionLocal, Device

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

class DeviceCreate(BaseModel):
    brand: str
    model: str
    category: Optional[str] = ""
    max_vpn_tunnels: Optional[int] = 0
    max_concurrent: Optional[int] = 0
    throughput_mbps: Optional[float] = 0
    recommended_users: Optional[str] = ""
    reference_price: Optional[float] = 0
    cost_price: Optional[float] = 0
    features: Optional[str] = ""
    notes: Optional[str] = ""

class DeviceUpdate(DeviceCreate):
    is_active: Optional[bool] = True

@router.get("/devices")
async def devices_page(request: Request):
    """設備管理 UI"""
    return templates.TemplateResponse("devices.html", {
        "request": request,
        "active_page": "devices"
    })

@router.get("/api/devices")
async def list_devices():
    """取得所有設備 (JSON)"""
    db = SessionLocal()
    try:
        devices = db.query(Device).order_by(Device.brand, Device.model).all()
        return {"devices": [d.to_dict() for d in devices]}
    finally:
        db.close()

@router.post("/api/devices")
async def create_device(data: DeviceCreate):
    """新增設備"""
    db = SessionLocal()
    try:
        device = Device(**data.dict())
        db.add(device)
        db.commit()
        return {"success": True, "message": "設備已新增"}
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)
    finally:
        db.close()

@router.put("/api/devices/{device_id}")
async def update_device(device_id: int, data: DeviceUpdate):
    """更新設備"""
    db = SessionLocal()
    try:
        device = db.query(Device).filter_by(id=device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
            
        for key, value in data.dict().items():
            setattr(device, key, value)
            
        db.commit()
        return {"success": True, "message": "設備已更新"}
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)
    finally:
        db.close()

@router.delete("/api/devices/{device_id}")
async def delete_device(device_id: int):
    """刪除設備"""
    db = SessionLocal()
    try:
        device = db.query(Device).filter_by(id=device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        db.delete(device)
        db.commit()
        return {"success": True, "message": "設備已刪除"}
    finally:
        db.close()
