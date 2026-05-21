import sqlite3

def upgrade_db():
    db = sqlite3.connect('database.db')
    try:
        db.execute('ALTER TABLE tenders ADD COLUMN bid_bond TEXT DEFAULT ""')
        print("tenders table altered")
    except sqlite3.OperationalError as e:
        print(f"tenders: {e}")

    try:
        db.execute('ALTER TABLE bidding_tenders ADD COLUMN bid_bond TEXT DEFAULT ""')
        print("bidding_tenders table altered")
    except sqlite3.OperationalError as e:
        print(f"bidding_tenders: {e}")

    db.commit()
    db.close()

if __name__ == "__main__":
    upgrade_db()
