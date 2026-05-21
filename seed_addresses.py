import os
import sys
import json
import random
from datetime import datetime
from pathlib import Path

# Add current directory to python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from models import SessionLocal, OrgContact, SalesInsight, Device

def main():
    print("Connecting to database...")
    db = SessionLocal()
    try:
        contacts = db.query(OrgContact).all()
        print(f"Found {len(contacts)} contacts in the database.")
        
        # Load devices to link realistic mock hardware
        devices = db.query(Device).all()
        device_dicts = [d.to_dict() for d in devices]
        
        # Address & GPS mapping for 27 contacts in Taiwan
        # We place them beautifully around Taipei and other regions to make LBS and distance calculation feel premium
        locations = [
            # Taipei region (close to Taipei 101 - lat=25.033976, lon=121.564478)
            {"address": "台北市信義區松仁路3號", "lat": 25.038100, "lng": 121.568300},
            {"address": "台北市中正區館前路46號", "lat": 25.045100, "lng": 121.513700},
            {"address": "台北市中山區北安路307號", "lat": 25.084100, "lng": 121.545800},
            {"address": "台北市大安區建國南路二段125號", "lat": 25.029800, "lng": 121.536700},
            {"address": "台北市信義區市府路1號", "lat": 25.037500, "lng": 121.563800},
            {"address": "台北市內湖區瑞光路399號", "lat": 25.074700, "lng": 121.572100},
            {"address": "台北市南港區園區街3號", "lat": 25.059200, "lng": 121.616300},
            {"address": "新北市板橋區中山路一段161號", "lat": 25.012400, "lng": 121.465100},
            {"address": "新北市新店區北新路三段200號", "lat": 24.978100, "lng": 121.539200},
            {"address": "基隆市中正區義一路1號", "lat": 25.132300, "lng": 121.744700},
            
            # Hsinchu / Taoyuan region (Medium distance)
            {"address": "桃園市桃園區縣府路1號", "lat": 24.993600, "lng": 121.301000},
            {"address": "桃園市龍潭區文化路1000號", "lat": 24.843600, "lng": 121.246400},
            {"address": "新竹市東區中正路120號", "lat": 24.806800, "lng": 120.968600},
            {"address": "新竹縣竹北市光明六路10號", "lat": 24.827200, "lng": 121.013500},
            {"address": "苗栗縣竹南鎮科研路35號", "lat": 24.695300, "lng": 120.895600},
            
            # Central & Southern region (Far distance)
            {"address": "台中市西屯區台灣大道四段1650號", "lat": 24.181800, "lng": 120.604700},
            {"address": "台中市西屯區台灣大道三段99號", "lat": 24.161800, "lng": 120.646900},
            {"address": "南投縣魚池鄉水社村中山路599號", "lat": 23.839400, "lng": 120.901100},
            {"address": "彰化縣彰化市中山路二段416號", "lat": 24.075600, "lng": 120.544700},
            {"address": "雲林縣斗六市大學路三段310號", "lat": 23.698300, "lng": 120.526200},
            {"address": "嘉義市東區中山路199號", "lat": 23.479100, "lng": 120.449800},
            {"address": "台南市安平區永華路二段6號", "lat": 22.990100, "lng": 120.186200},
            {"address": "高雄市苓雅區四維三路2號", "lat": 22.620600, "lng": 120.312100},
            {"address": "屏東縣屏東市自由路527號", "lat": 22.676100, "lng": 120.485900},
            
            # Eastern region
            {"address": "宜蘭縣宜蘭市縣政北路1號", "lat": 24.730600, "lng": 121.763400},
            {"address": "花蓮縣花蓮市府前路17號", "lat": 23.992800, "lng": 121.624700},
            {"address": "台東縣台東市中山路276號", "lat": 22.755800, "lng": 121.150400}
        ]

        # Specific maps for key known organizations to look professional
        org_specific_locations = {
            "國防部空軍司令部": {"address": "台北市中山區北安路307號", "lat": 25.084100, "lng": 121.545800},
            "國家原子能科技研究院": {"address": "桃園市龍潭區佳安里文化路1000號", "lat": 24.843600, "lng": 121.246400},
            "財團法人國家衛生研究院": {"address": "苗栗縣竹南鎮科研路35號", "lat": 24.695300, "lng": 120.895600},
            "台灣中油股份有限公司": {"address": "台北市信義區松仁路3號", "lat": 25.038100, "lng": 121.568300},
            "臺灣土地銀行股份有限公司": {"address": "台北市中正區館前路46號", "lat": 25.045100, "lng": 121.513700},
            "臺中榮民總醫院": {"address": "台中市西屯區台灣大道四段1650號", "lat": 24.181800, "lng": 120.604700},
            "新竹縣教育研究發展暨網路中心": {"address": "新竹縣竹北市光明六路10號", "lat": 24.827200, "lng": 121.013500},
            "台灣電力股份有限公司明潭發電廠": {"address": "南投縣魚池鄉水社村中山路599號", "lat": 23.839400, "lng": 120.901100}
        }

        updated_contacts = 0
        created_insights = 0

        for i, c in enumerate(contacts):
            # 1. Update address and GPS
            loc = None
            for name, specific_loc in org_specific_locations.items():
                if name in c.org_name:
                    loc = specific_loc
                    break
            
            if not loc:
                # Assign a distributed location
                loc = locations[i % len(locations)]

            c.address = loc["address"]
            c.latitude = loc["lat"]
            c.longitude = loc["lng"]
            db.add(c)
            updated_contacts += 1

            # 2. Check and Create SalesInsight if c.source_tender_id is present
            if c.source_tender_id:
                insight = db.query(SalesInsight).filter_by(tender_id=c.source_tender_id).first()
                if not insight:
                    # Create a realistic sales insight
                    remote_score = random.randint(45, 92)
                    users = random.choice([30, 50, 80, 100, 150, 200, 300])
                    bandwidth = users * 2 # 2 Mbps per user
                    
                    # Choose a device model to recommend
                    selected_device = random.choice(device_dicts) if device_dicts else {
                        "brand": "Fortinet", "model": "FortiGate 60F", "cost_price": 120000, "reference_price": 125000
                    }
                    
                    # Calculate recommended price:建议標價 = 成本價 / (1.0 - 目標毛利率)
                    margin_rate = 0.15
                    cost_price = selected_device.get("cost_price", 120000)
                    if cost_price == 0:
                        cost_price = selected_device.get("reference_price", 35000) * 0.7
                    
                    suggested_price = int(cost_price / (1.0 - margin_rate))
                    
                    insight = SalesInsight(
                        tender_id=c.source_tender_id,
                        source_table="tenders" if "招標" not in c.tags else "bidding_tenders",
                        org_name=c.org_name,
                        org_tax_id=c.org_tax_id or f"88{random.randint(100000, 999999)}",
                        
                        # Module A
                        remote_score=remote_score,
                        remote_job_count=random.randint(0, 5),
                        netadmin_job_count=random.randint(1, 3),
                        total_job_count=random.randint(2, 20),
                        job_analysis_json=json.dumps({"WFH": "High Potential", "NetAdmin": "Required"}),
                        job_analyzed_at=datetime.now(),
                        
                        # Module B
                        estimated_users=users,
                        vpn_bandwidth_mbps=bandwidth,
                        recommended_devices_json=json.dumps([selected_device]),
                        device_match_reason=f"依據 {users} 使用者人數匹配性價比最優型號",
                        device_matched_at=datetime.now(),
                        
                        # Module C
                        market_price=selected_device.get("reference_price", 125000),
                        suggested_bid_price=suggested_price,
                        margin_rate="0.15",
                        price_source="硬體成本加乘估算",
                        price_updated_at=datetime.now()
                    )
                    db.add(insight)
                    created_insights += 1

        db.commit()
        print(f"[SUCCESS] Successfully updated {updated_contacts} contacts with realistic Taiwanese addresses and GPS.")
        print(f"[SUCCESS] Successfully created {created_insights} SalesInsight records linked to contacts.")
        
    except Exception as e:
        print(f"[FAILED] Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
