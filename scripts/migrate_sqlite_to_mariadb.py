import sys
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config import config
from models import (
    Base, Tender, BiddingTender, OrgContact, ContactLog, 
    Device, PriceHistory, SalesInsight, ScrapeLog, AnalysisLog
)

sqlite_path = BASE_DIR / "database.db"
if not sqlite_path.exists():
    sqlite_path = BASE_DIR / "data" / "database.db"

print("SOURCE SQLITE DB:", sqlite_path, "EXISTS:", sqlite_path.exists())
print("TARGET MARIADB URL:", config.DATABASE_URL)

if not sqlite_path.exists():
    print("NO SQLITE DB FOUND TO MIGRATE.")
    sys.exit(0)

sqlite_engine = create_engine(f"sqlite:///{sqlite_path}")
mariadb_engine = create_engine(config.DATABASE_URL)

# Ensure target database tables exist
Base.metadata.create_all(mariadb_engine)

SqliteSession = sessionmaker(bind=sqlite_engine)
MariadbSession = sessionmaker(bind=mariadb_engine)

s_db = SqliteSession()
m_db = MariadbSession()

models_list = [
    ("tenders", Tender),
    ("bidding_tenders", BiddingTender),
    ("org_contacts", OrgContact),
    ("contact_logs", ContactLog),
    ("devices", Device),
    ("price_history", PriceHistory),
    ("sales_insights", SalesInsight),
    ("scrape_logs", ScrapeLog),
    ("analysis_logs", AnalysisLog),
]

summary = {}

try:
    for table_name, model_cls in models_list:
        rows = s_db.query(model_cls).all()
        migrated_count = 0
        for r in rows:
            data = {c.name: getattr(r, c.name) for c in model_cls.__table__.columns}
            
            existing = m_db.query(model_cls).filter_by(id=data["id"]).first()
            if not existing:
                new_obj = model_cls(**data)
                m_db.add(new_obj)
                migrated_count += 1
                
        m_db.commit()
        summary[table_name] = (len(rows), migrated_count)
        print(f"Migrated {table_name}: {migrated_count} new / {len(rows)} total")

    print("\n" + "=" * 50)
    print("MIGRATION COMPLETED SUCCESSFULLY!")
    for t, (tot, mig) in summary.items():
        print(f"  - {t}: {mig} migrated ({tot} in SQLite)")
    print("=" * 50)
except Exception as e:
    m_db.rollback()
    print("MIGRATION ERROR:", e)
finally:
    s_db.close()
    m_db.close()
