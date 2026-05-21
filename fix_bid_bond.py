import sqlite3
import re

def fix_db():
    db = sqlite3.connect('database.db')
    cursor = db.cursor()

    def fix_table(table_name):
        cursor.execute(f"SELECT id, bid_bond FROM {table_name}")
        rows = cursor.fetchall()
        for row_id, bid_bond in rows:
            if not bid_bond or bid_bond in ("無", "有"):
                continue
                
            match = re.search(r'^(.+?)(?:機關押標金|。|；|$)', bid_bond)
            if match:
                res = match.group(1).replace("一定金額：", "").replace("一定金額:", "").strip()
                if re.match(r'^\d+$', res):
                    res = f"{int(res):,}元"
                elif re.match(r'^\d+(,\d+)+$', res):
                    res = f"{res}元"
                
                if res != bid_bond:
                    cursor.execute(f"UPDATE {table_name} SET bid_bond = ? WHERE id = ?", (res, row_id))
                    print(f"Fixed {table_name} id {row_id}: {bid_bond[:20]}... -> {res}")

    fix_table("tenders")
    fix_table("bidding_tenders")
    db.commit()
    db.close()

if __name__ == "__main__":
    fix_db()
