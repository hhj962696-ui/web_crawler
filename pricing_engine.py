"""
模組 C: 動態比價與報價引擎
"""

import logging
from datetime import datetime, timedelta
from models import SessionLocal, Device, PriceHistory

logger = logging.getLogger(__name__)

def calculate_bid_price(cost_price: float, margin_rate: float = 0.15) -> float:
    """
    根據成本價與目標毛利率，推算建議標價。
    公式: suggested_price = cost_price / (1 - margin_rate)
    """
    if margin_rate >= 1.0 or margin_rate < 0:
        logger.error(f"無效的毛利率: {margin_rate}")
        return cost_price

    suggested_price = cost_price / (1.0 - margin_rate)
    return round(suggested_price, 2)

def record_price(device_id: int, price: float, price_type: str = "market", source: str = "", tender_id: str = "") -> bool:
    """
    記錄設備的市場參考價或歷史決標價
    price_type: 'market' (市場價), 'bid_award' (決標價), 'ecommerce' (電商價)
    """
    db = SessionLocal()
    try:
        device = db.query(Device).filter_by(id=device_id).first()
        if not device:
            logger.error(f"設備不存在 (ID: {device_id})")
            return False
            
        history = PriceHistory(
            device_id=device_id,
            price=price,
            price_type=price_type,
            source=source,
            tender_id=tender_id
        )
        db.add(history)
        
        # 若為 market 且價格大於 0，可選擇同步更新 reference_price，此處暫不同步避免影響既有資料
        
        db.commit()
        return True
    except Exception as e:
        logger.error(f"記錄價格失敗 (Device ID: {device_id}): {e}", exc_info=True)
        return False
    finally:
        db.close()

def get_price_trend(device_id: int, days: int = 90) -> list:
    """
    取得過去 N 天內的價格歷史趨勢
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now() - timedelta(days=days)
        history = db.query(PriceHistory).filter(
            PriceHistory.device_id == device_id,
            PriceHistory.recorded_at >= cutoff
        ).order_by(PriceHistory.recorded_at.asc()).all()
        
        return [h.to_dict() for h in history]
    finally:
        db.close()
