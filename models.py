"""
資料庫模型模組
使用 SQLAlchemy ORM 定義資料表結構
"""

from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Text,
    Boolean, DateTime, event
)
from sqlalchemy.orm import declarative_base, sessionmaker
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
            "scraped_at": self.scraped_at.strftime("%Y-%m-%d %H:%M") if self.scraped_at else "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M") if self.updated_at else "",
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


# 建立資料庫引擎與 Session
engine = create_engine(config.DATABASE_URL, echo=False)


# 啟用 SQLite WAL 模式，提升並行讀寫效能
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine)


def init_db():
    """初始化資料庫，建立所有資料表"""
    Base.metadata.create_all(engine)


def get_db():
    """取得資料庫 session（用於 FastAPI 依賴注入）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
