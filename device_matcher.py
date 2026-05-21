"""
模組 B: 需求計算與設備匹配引擎
"""

import json
from datetime import datetime
from models import SessionLocal, Device

def calculate_vpn_requirements(estimated_users: int):
    """
    根據預估人數計算 VPN 需求。
    假設同時上線率為 70%，每人需要 2Mbps 頻寬。
    """
    concurrent_vpn = int(estimated_users * 0.7)
    bandwidth_mbps = concurrent_vpn * 2.0
    return concurrent_vpn, bandwidth_mbps

def match_devices(estimated_users: int, budget: float = None):
    """
    自動匹配適合的設備。
    回傳：(推薦設備清單 JSON字串, 推薦理由字串)
    """
    if estimated_users <= 0:
        return "[]", "無有效人數預估，無法進行匹配。"

    concurrent_vpn, bandwidth_mbps = calculate_vpn_requirements(estimated_users)
    
    db = SessionLocal()
    try:
        # 尋找支援所需 VPN 通道數的啟用的設備
        query = db.query(Device).filter(
            Device.is_active == True,
            Device.max_vpn_tunnels >= concurrent_vpn
        )
        
        if budget:
            query = query.filter(Device.reference_price <= budget)
            
        # 按照價格由低至高排序，取前三名最具性價比的
        matched = query.order_by(Device.reference_price.asc()).limit(3).all()
        
        if not matched:
            reason = f"預估 {estimated_users} 人（需 {concurrent_vpn} VPN 連線，頻寬 {bandwidth_mbps} Mbps）。目前資料庫中找不到符合規格或預算的設備。"
            return "[]", reason
            
        device_list = []
        for d in matched:
            device_list.append({
                "id": d.id,
                "brand": d.brand,
                "model": d.model,
                "max_vpn_tunnels": d.max_vpn_tunnels,
                "reference_price": d.reference_price
            })
            
        recommended_models = ", ".join([f"{d.brand} {d.model}" for d in matched])
        reason = f"預估 {estimated_users} 人（需 {concurrent_vpn} VPN 連線，頻寬 {bandwidth_mbps} Mbps）。推薦最具性價比的設備：{recommended_models}。"
        
        return json.dumps(device_list, ensure_ascii=False), reason
        
    finally:
        db.close()
