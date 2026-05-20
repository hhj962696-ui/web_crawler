"""
單次執行爬蟲（供 Windows 工作排程器使用）
當 run.py 未常駐時，可由系統定時呼叫此腳本。
"""

import io
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def main():
    from models import init_db
    from scraper import run_scraper

    init_db()
    result = run_scraper(scrape_type="daily")
    print(result)
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
