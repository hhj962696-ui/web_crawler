"""
資料庫模型模組
使用 SQLAlchemy ORM 定義資料表結構
"""

from datetime import datetime

from time_utils import format_tw, discord_timestamp
from sqlalchemy import (
    create_engine, Column, Integer, String, Text,
    Boolean, DateTime, event, Float, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from config import config

Base = declarative_base()


class Tender(Base):
    """公開徵求案件資料表"""
    __tablename__ = "tenders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tender_id = Column(String(100), unique=True, nullable=False, index=True)  # 案號
    tender_name = Column(Text, nullable=False)  # 案名
    org_name = Column(String(200), default="")  # 招標機關
    contact_person = Column(String(100), default="")  # 承辦人
    phone = Column(String(50), default="")  # 電話
    budget = Column(String(100), default="")  # 預算金額
    tender_url = Column(Text, default="")  # 連結
    status = Column(String(50), default="公開徵求")  # 案件狀態
    is_tracked = Column(Boolean, default=False, index=True)  # 是否被追蹤
    track_note = Column(Text, default="")  # 追蹤備註
    bid_bond = Column(String(100), default="")  # 押標金
    scraped_at = Column(DateTime, default=datetime.now)  # 爬取時間
    created_at = Column(DateTime, default=datetime.now)  # 建立時間
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)  # 更新時間

    def to_dict(self):
        """轉換為字典"""
        return {
            "id": self.id,
            "tender_id": self.tender_id,
            "tender_name": self.tender_name,
            "org_name": self.org_name,
            "contact_person": self.contact_person,
            "phone": self.phone,
            "budget": self.budget,
            "tender_url": self.tender_url,
            "status": self.status,
            "is_tracked": self.is_tracked,
            "track_note": self.track_note,
            "bid_bond": self.bid_bond,
            "scraped_at": format_tw(self.scraped_at),
            "scraped_at_iso": discord_timestamp(self.scraped_at),
            "created_at": format_tw(self.created_at),
            "updated_at": format_tw(self.updated_at),
        }


class BiddingTender(Base):
    """公開招標案件資料表"""
    __tablename__ = "bidding_tenders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tender_id = Column(String(100), unique=True, nullable=False, index=True)
    tender_name = Column(Text, nullable=False)
    org_name = Column(String(200), default="")
    contact_person = Column(String(100), default="")
    phone = Column(String(50), default="")
    budget = Column(String(100), default="")
    tender_url = Column(Text, default="")
    status = Column(String(50), default="公開招標")
    proctrg_cate = Column(String(50), default="")  # 工程類 / 財物類 / 勞務類
    bid_deadline = Column(String(50), default="")  # 截止投標
    tender_way = Column(String(50), default="")  # 招標方式
    is_tracked = Column(Boolean, default=False, index=True)
    track_note = Column(Text, default="")
    bid_bond = Column(String(100), default="")
    scraped_at = Column(DateTime, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "tender_id": self.tender_id,
            "tender_name": self.tender_name,
            "org_name": self.org_name,
            "contact_person": self.contact_person,
            "phone": self.phone,
            "budget": self.budget,
            "tender_url": self.tender_url,
            "status": self.status,
            "proctrg_cate": self.proctrg_cate,
            "bid_deadline": self.bid_deadline,
            "tender_way": self.tender_way,
            "is_tracked": self.is_tracked,
            "track_note": self.track_note,
            "bid_bond": self.bid_bond,
            "scraped_at": format_tw(self.scraped_at),
            "scraped_at_iso": discord_timestamp(self.scraped_at),
            "created_at": format_tw(self.created_at),
            "updated_at": format_tw(self.updated_at),
        }


class ScrapeLog(Base):
    """爬蟲執行紀錄資料表"""
    __tablename__ = "scrape_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, default=datetime.now)
    finished_at = Column(DateTime, nullable=True)
    total_found = Column(Integer, default=0)  # 找到的案件數
    new_count = Column(Integer, default=0)  # 新案件數
    updated_count = Column(Integer, default=0)  # 更新案件數
    status = Column(String(20), default="running")  # running / success / error
    error_message = Column(Text, default="")
    scrape_type = Column(String(20), default="daily")  # daily / track_check / manual

    def to_dict(self):
        """轉換為字典"""
        return {
            "id": self.id,
            "started_at": self.started_at.strftime("%Y-%m-%d %H:%M:%S") if self.started_at else "",
            "finished_at": self.finished_at.strftime("%Y-%m-%d %H:%M:%S") if self.finished_at else "",
            "total_found": self.total_found,
            "new_count": self.new_count,
            "updated_count": self.updated_count,
            "status": self.status,
            "error_message": self.error_message,
            "scrape_type": self.scrape_type,
        }


class SalesInsight(Base):
    """業務洞察主表 — 整合模組 A/B/C 的分析結果"""
    __tablename__ = "sales_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tender_id = Column(String(100), unique=True, nullable=False, index=True)
    source_table = Column(String(20), default="tenders")  # 'tenders' | 'bidding_tenders'
    org_name = Column(String(200), default="")
    org_tax_id = Column(String(20), default="")

    # 模組 A：104 探測結果
    remote_score = Column(Integer, default=0)          # 遠端工作潛力分數 0~100
    remote_job_count = Column(Integer, default=0)      # 遠端/WFH 職缺數
    netadmin_job_count = Column(Integer, default=0)    # 網管/MIS 職缺數
    total_job_count = Column(Integer, default=0)       # 該機關總職缺數
    job_analysis_json = Column(Text, default="")       # 分析明細 JSON
    job_analyzed_at = Column(DateTime, nullable=True)   # 上次 104 分析時間
    skip_reason = Column(String(100), default="")      # 略過原因（學校/中研院等）

    # 模組 B：設備匹配結果
    estimated_users = Column(Integer, default=0)
    vpn_bandwidth_mbps = Column(Integer, default=0)
    recommended_devices_json = Column(Text, default="[]")
    device_match_reason = Column(Text, default="")
    device_matched_at = Column(DateTime, nullable=True)

    # 模組 C：報價結果
    market_price = Column(Integer, default=0)
    suggested_bid_price = Column(Integer, default=0)
    margin_rate = Column(String(10), default="0.15")
    price_source = Column(String(200), default="")
    price_updated_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "tender_id": self.tender_id,
            "source_table": self.source_table,
            "org_name": self.org_name,
            "org_tax_id": self.org_tax_id,
            "remote_score": self.remote_score,
            "remote_job_count": self.remote_job_count,
            "netadmin_job_count": self.netadmin_job_count,
            "total_job_count": self.total_job_count,
            "job_analysis_json": self.job_analysis_json,
            "job_analyzed_at": format_tw(self.job_analyzed_at) if self.job_analyzed_at else "",
            "skip_reason": self.skip_reason,
            "estimated_users": self.estimated_users,
            "vpn_bandwidth_mbps": self.vpn_bandwidth_mbps,
            "recommended_devices_json": self.recommended_devices_json,
            "device_match_reason": self.device_match_reason,
            "device_matched_at": format_tw(self.device_matched_at) if self.device_matched_at else "",
            "market_price": self.market_price,
            "suggested_bid_price": self.suggested_bid_price,
            "margin_rate": self.margin_rate,
            "price_source": self.price_source,
            "price_updated_at": format_tw(self.price_updated_at) if self.price_updated_at else "",
            "created_at": format_tw(self.created_at),
            "updated_at": format_tw(self.updated_at),
        }


class Device(Base):
    """設備型號資料庫"""
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand = Column(String(50), nullable=False)            # 品牌
    model = Column(String(100), nullable=False)           # 型號
    category = Column(String(50), default="")             # 類別 (防火牆/路由器/AP/交換器)
    max_vpn_tunnels = Column(Integer, default=0)          # 最大 VPN 通道數
    max_concurrent = Column(Integer, default=0)           # 最大並行連線數
    throughput_mbps = Column(Integer, default=0)           # 吞吐量 (Mbps)
    recommended_users = Column(String(50), default="")    # 適用規模
    reference_price = Column(Integer, default=0)          # 參考售價
    cost_price = Column(Integer, default=0)               # 成本價
    features = Column(Text, default="")                   # 特色功能 (JSON)
    notes = Column(Text, default="")                      # 備註
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "brand": self.brand,
            "model": self.model,
            "category": self.category,
            "max_vpn_tunnels": self.max_vpn_tunnels,
            "max_concurrent": self.max_concurrent,
            "throughput_mbps": self.throughput_mbps,
            "recommended_users": self.recommended_users,
            "reference_price": self.reference_price,
            "cost_price": self.cost_price,
            "features": self.features,
            "notes": self.notes,
            "is_active": self.is_active,
            "created_at": format_tw(self.created_at),
            "updated_at": format_tw(self.updated_at),
        }


class PriceHistory(Base):
    """價格歷史紀錄"""
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(Integer, nullable=True)            # 關聯設備
    tender_id = Column(String(100), default="")           # 關聯案號（決標價）
    price_type = Column(String(20), default="market")     # 'market' | 'bid_award' | 'ecommerce'
    price = Column(Integer, nullable=False)
    source = Column(String(200), default="")              # 來源 URL 或說明
    recorded_at = Column(DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "tender_id": self.tender_id,
            "price_type": self.price_type,
            "price": self.price,
            "source": self.source,
            "recorded_at": format_tw(self.recorded_at),
        }


class OrgContact(Base):
    """企業通訊錄"""
    __tablename__ = "org_contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_name = Column(String(200), nullable=False)
    org_tax_id = Column(String(20), default="")
    contact_name = Column(String(100), default="")
    title = Column(String(100), default="")
    phone = Column(String(50), default="")
    mobile = Column(String(50), default="")
    email = Column(String(200), default="")
    address = Column(String(500), default="")
    department = Column(String(100), default="")
    source_tender_id = Column(String(100), default="")
    tags = Column(String(500), default="")
    notes = Column(Text, default="")
    is_active = Column(Boolean, default=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 關聯聯絡人互動紀錄 (依時間由新到舊排序)
    interaction_logs = relationship("ContactLog", back_populates="contact", cascade="all, delete-orphan", order_by="desc(ContactLog.created_at)")

    def to_dict(self):
        return {
            "id": self.id,
            "org_name": self.org_name,
            "org_tax_id": self.org_tax_id,
            "contact_name": self.contact_name,
            "title": self.title,
            "phone": self.phone,
            "mobile": self.mobile,
            "email": self.email,
            "address": self.address,
            "department": self.department,
            "source_tender_id": self.source_tender_id,
            "tags": self.tags,
            "notes": self.notes,
            "is_active": self.is_active,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "interaction_logs": [log.to_dict() for log in self.interaction_logs] if self.interaction_logs else [],
            "created_at": format_tw(self.created_at),
            "updated_at": format_tw(self.updated_at),
        }


class ContactLog(Base):
    """聯絡人互動紀錄資料表"""
    __tablename__ = "contact_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(Integer, ForeignKey("org_contacts.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    content_text = Column(Text, default="")
    voice_url = Column(String(500), default="")

    contact = relationship("OrgContact", back_populates="interaction_logs")

    def to_dict(self):
        return {
            "id": self.id,
            "contact_id": self.contact_id,
            "created_at": format_tw(self.created_at),
            "content_text": self.content_text,
            "voice_url": self.voice_url,
        }


class AnalysisLog(Base):
    """分析執行紀錄"""
    __tablename__ = "analysis_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tender_id = Column(String(100), default="")
    module = Column(String(20), nullable=False)           # 'job104' | 'device' | 'pricing'
    status = Column(String(20), default="running")        # 'running' | 'success' | 'error' | 'skipped'
    message = Column(Text, default="")
    started_at = Column(DateTime, default=datetime.now)
    finished_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "tender_id": self.tender_id,
            "module": self.module,
            "status": self.status,
            "message": self.message,
            "started_at": format_tw(self.started_at),
            "finished_at": format_tw(self.finished_at) if self.finished_at else "",
        }


# 建立資料庫引擎與 Session
engine = create_engine(config.DATABASE_URL, echo=False)


# 啟用 SQLite WAL 模式，提升並行讀寫效能（若在 Synology NAS 等不支援 WAL 鎖定之檔案系統，自動降級為 DELETE 模式）
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    except Exception as e:
        import sys
        print(f"[Warning] Failed to set SQLite journal_mode=WAL ({e}). Falling back to default journal mode.", file=sys.stderr)
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    except Exception as e:
        import sys
        print(f"[Warning] Failed to set SQLite foreign_keys=ON ({e})", file=sys.stderr)
    cursor.close()



SessionLocal = sessionmaker(bind=engine)


def init_db():
    """初始化資料庫，建立所有資料表，並自動執行欄位擴充遷移 (Auto-Migration)"""
    Base.metadata.create_all(engine)
    
    # === SQLite 通用自動欄位遷移系統 ===
    from sqlalchemy import text
    from sqlalchemy import Integer, Float, Boolean, DateTime
    db = SessionLocal()
    try:
        for table_name, table_obj in Base.metadata.tables.items():
            # 取得該資料表在 SQLite 中目前已存在的欄位
            result = db.execute(text(f"PRAGMA table_info({table_name})"))
            existing_cols = {row[1] for row in result.fetchall()}
            
            if not existing_cols:
                # 該資料表不存在於 SQLite 中（通常 create_all 會處理，跳過）
                continue
                
            # 比對 SQLAlchemy 模型中定義的所有欄位
            for col_name, col_obj in table_obj.columns.items():
                if col_name not in existing_cols:
                    # 判斷對應的 SQLite 欄位資料型態
                    t = col_obj.type
                    if isinstance(t, Integer):
                        sql_type = "INTEGER"
                    elif isinstance(t, Float):
                        sql_type = "FLOAT"
                    elif isinstance(t, Boolean):
                        sql_type = "BOOLEAN"
                    elif isinstance(t, DateTime):
                        sql_type = "DATETIME"
                    else:
                        sql_type = "TEXT"
                        
                    # 預設值處理
                    default_str = ""
                    if col_obj.default is not None and hasattr(col_obj.default, "arg"):
                        val = col_obj.default.arg
                        if isinstance(val, (int, float)):
                            default_str = f" DEFAULT {val}"
                        elif isinstance(val, bool):
                            default_str = f" DEFAULT {1 if val else 0}"
                        elif isinstance(val, str):
                            default_str = f" DEFAULT '{val}'"
                            
                    # 執行 ALTER TABLE 語法新增欄位
                    alter_query = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sql_type}{default_str}"
                    db.execute(text(alter_query))
                    db.commit()
                    print(f"Database Migration: Added column '{col_name}' ({sql_type}) to table '{table_name}'.")
    except Exception as e:
        print(f"Database Migration Warning: {e}")
        db.rollback()
    finally:
        db.close()



def get_db():
    """取得資料庫 session（用於 FastAPI 依賴注入）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
