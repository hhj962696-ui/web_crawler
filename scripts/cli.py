"""
命令列測試工具（不需瀏覽器、不需 XAMPP）
用法範例：
  python scripts/cli.py status
  python scripts/cli.py test-discord
  python scripts/cli.py scrape
  python scripts/cli.py list --limit 10
  python scripts/cli.py export -o tenders.csv
"""

import argparse
import csv
import io
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    import io as _io
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def ensure_db():
    """建立 SQLite 資料表（若尚未存在）"""
    from models import init_db
    init_db()


def cmd_init_db(_args):
    from config import config
    print(f"資料庫已就緒: {config.DB_PATH}")
    return 0


def cmd_status(_args):
    from config import config
    from models import SessionLocal, Tender, ScrapeLog
    from sqlalchemy import func, desc

    db = SessionLocal()
    try:
        total = db.query(func.count(Tender.id)).scalar() or 0
        tracked = db.query(func.count(Tender.id)).filter(Tender.is_tracked == True).scalar() or 0
        last = db.query(ScrapeLog).order_by(desc(ScrapeLog.started_at)).first()

        print("=== 系統狀態 ===")
        print(f"資料庫     : {config.DB_PATH}")
        print(f"案件總數   : {total}")
        print(f"追蹤中     : {tracked}")
        print(f"關鍵字     : {', '.join(config.FILTER_KEYWORDS) or '(未設定，全抓)'}")
        print(f"回溯天數   : {config.SCRAPE_LOOKBACK_DAYS}")
        from models import BiddingTender
        bidding_total = db.query(func.count(BiddingTender.id)).scalar() or 0

        print(f"排程徵求   : {config.SCRAPE_SCHEDULE_HOUR:02d}:{config.SCRAPE_SCHEDULE_MINUTE:02d}")
        print(f"排程招標   : {config.BIDDING_SCHEDULE_HOUR:02d}:{config.BIDDING_SCHEDULE_MINUTE:02d}")
        print(f"招標回溯   : {config.BIDDING_LOOKBACK_DAYS} 天")
        print(f"招標性質   : {','.join(config.BIDDING_PROC_CATEGORIES) or '(不限)'}")
        print(f"招標案件   : {bidding_total}")
        print(f"追蹤檢查   : {config.TRACK_CHECK_HOUR:02d}:{config.TRACK_CHECK_MINUTE:02d}")
        print(f"Discord徵求: {'已設定' if config.DISCORD_WEBHOOK_URL else '未設定'}")
        print(f"Discord招標: {'已設定' if config.BIDDING_DISCORD_WEBHOOK_URL else '未設定'}")
        print(f"Chrome     : {'無頭模式' if config.CHROME_HEADLESS else '顯示視窗'}")

        if last:
            print(f"\n最近執行   : {last.scrape_type} / {last.status}")
            print(f"  開始     : {last.started_at}")
            print(f"  結束     : {last.finished_at or '-'}")
            print(f"  找到/新增: {last.total_found} / {last.new_count}")
            if last.error_message:
                print(f"  錯誤     : {last.error_message[:300]}")
        else:
            print("\n尚無爬蟲執行紀錄")
    finally:
        db.close()


def cmd_check_network(_args):
    from network_check import check_pcc_network
    from config import config

    print("正在檢測政府採購網連線...")
    print(f"目標: {config.PCC_BASE_URL}")
    if config.HTTPS_PROXY or config.HTTP_PROXY:
        print(f"Proxy: {config.HTTPS_PROXY or config.HTTP_PROXY}")

    net = check_pcc_network(timeout=25)
    print(f"\n結果: {'通過' if net['ok'] else '失敗'}")
    print(f"說明: {net['message']}")
    if net.get("detail"):
        print(f"細節: {net['detail']}")

    if not net["ok"]:
        print("\n--- 建議排查 ---")
        print("1. 用 Chrome 手動開啟: https://web.pcc.gov.tw")
        print("2. 若公司網路需 Proxy，在 .env 設定 HTTPS_PROXY=http://主機:埠")
        print("3. 關閉 VPN 或改連手機熱點再試")
        print("4. Chrome 訊息中的 GPU / GCM / TensorFlow 可忽略")
        print("5. SSL net_error -101 代表連線被重置，多半是網路/防火牆問題")
        return 1

    print("\n網路正常，可執行: python scripts/cli.py scrape")
    return 0


def cmd_notify_preview(args):
    from models import SessionLocal, Tender
    from sqlalchemy import desc
    from discord_notifier import send_tenders_preview

    db = SessionLocal()
    try:
        rows = (
            db.query(Tender)
            .order_by(desc(Tender.created_at))
            .limit(args.limit)
            .all()
        )
        if not rows:
            print("資料庫無案件，請先執行 scrape")
            return 1
        tenders = [r.to_dict() for r in rows]
    finally:
        db.close()

    print(f"正在發送 {len(tenders)} 筆預覽通知到 Discord...")
    ok = send_tenders_preview(tenders)
    if ok:
        print("已發送！請到 Discord 查看排版，滿意後新案會自動使用相同格式。")
        return 0
    print("發送失敗，請檢查 Webhook")
    return 1


def cmd_test_discord(_args):
    from discord_notifier import send_test_notification

    print("正在發送 Discord 測試通知...")
    ok = send_test_notification()
    if ok:
        print("成功！請到 Discord 頻道確認。")
        return 0
    print("失敗。請檢查 .env 的 DISCORD_WEBHOOK_URL")
    return 1


def cmd_scrape_bidding(args):
    from bidding_scraper import run_bidding_scraper
    from network_check import check_pcc_network

    if not args.force:
        print("先檢測政府採購網連線...")
        net = check_pcc_network(timeout=25)
        if not net["ok"]:
            print(f"失敗: {net['message']}")
            return 1
        print(f"通過: {net['message']}\n")

    print("開始公開招標爬蟲（需 1～5 分鐘）...")
    result = run_bidding_scraper(
        scrape_type="bidding_manual",
        use_filter=not args.no_filter,
    )
    print("\n=== 公開招標爬蟲結果 ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
    return 0 if result.get("success") else 1


def cmd_list_bidding(args):
    from models import BiddingTender
    from sqlalchemy import desc

    db = SessionLocal()
    try:
        rows = (
            db.query(BiddingTender)
            .order_by(desc(BiddingTender.created_at))
            .limit(args.limit)
            .all()
        )
        if not rows:
            print("尚無公開招標案件。請執行: python scripts/cli.py scrape-bidding")
            return 0
        print(f"=== 最近 {len(rows)} 筆公開招標 ===\n")
        for i, t in enumerate(rows, 1):
            d = t.to_dict()
            print(f"[{i}] {d['tender_name'][:60]}")
            print(f"    案號: {d['tender_id']}  性質: {d['proctrg_cate'] or 'N/A'}")
            print(f"    機關: {d['org_name'] or 'N/A'}")
            print(f"    預算: {d['budget'] or '未公告'}  截止: {d['bid_deadline'] or 'N/A'}")
            print(f"    建立: {d['created_at']}")
            if d["tender_url"]:
                print(f"    連結: {d['tender_url']}")
            print()
    finally:
        db.close()
    return 0


def cmd_scrape(args):
    from scraper import run_scraper
    from network_check import check_pcc_network

    if not args.force:
        print("先檢測政府採購網連線...")
        net = check_pcc_network(timeout=25)
        if not net["ok"]:
            print(f"失敗: {net['message']}")
            if net.get("detail"):
                print(f"細節: {net['detail']}")
            print("若確定瀏覽器可開啟該網站，可加 --force 強制執行爬蟲")
            return 1
        print(f"通過: {net['message']}\n")

    print("開始爬蟲（需 1～5 分鐘，請稍候；Chrome 紅字訊息多半可忽略）...")
    result = run_scraper(
        scrape_type="manual",
        use_filter=not args.no_filter,
    )
    print("\n=== 爬蟲結果 ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
    return 0 if result.get("success") else 1


def cmd_repair_phones(_args):
    from scraper import repair_stored_phones

    print("修正資料庫中異常電話欄位（公開徵求 + 公開招標）...")
    result = repair_stored_phones()
    print("\n=== 電話修正結果 ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
    total = result.get("tenders_fixed", 0) + result.get("bidding_fixed", 0)
    if total:
        print("\n請重新整理瀏覽器頁面查看更新。")
    return 0 if result.get("success") else 1


def cmd_enrich_bidding(_args):
    from scraper import repair_stored_phones
    from bidding_scraper import enrich_bidding_contacts

    print("1/2 先修正已存異常電話...")
    repair = repair_stored_phones()
    print(f"   招標修正 {repair.get('bidding_fixed', 0)} 筆")

    print("2/2 補抓公開招標詳情頁（承辦人/電話）...")
    result = enrich_bidding_contacts()
    print("\n=== 公開招標補抓結果 ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
    if result.get("no_url"):
        print("\n提示：若 no_url > 0，請先執行 scrape-bidding 更新連結")
    print("\n請重新整理瀏覽器「公開招標」分頁查看更新。")
    return 0 if result.get("success") else 1


def cmd_enrich(_args):
    from scraper import enrich_missing_contacts, repair_stored_phones

    print("1/2 先修正已存異常電話...")
    repair_stored_phones()

    print("2/2 補抓公開徵求承辦人/電話（需已存有詳情頁連結）...")
    result = enrich_missing_contacts()
    print("\n=== 公開徵求補抓結果 ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
    if result.get("no_url"):
        print("\n提示：若 no_url > 0，請先執行 python scripts/cli.py scrape 更新連結後再 enrich")
    print("\n公開招標請改用: python scripts/cli.py enrich-bidding")
    return 0 if result.get("success") else 1


def cmd_check_tracked(_args):
    from scraper import check_tracked_tenders

    print("檢查追蹤案件...")
    result = check_tracked_tenders()
    print("\n=== 追蹤檢查結果 ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
    return 0 if result.get("success") else 1


def cmd_list(args):
    from models import SessionLocal, Tender
    from sqlalchemy import desc

    db = SessionLocal()
    try:
        rows = (
            db.query(Tender)
            .order_by(desc(Tender.created_at))
            .limit(args.limit)
            .all()
        )
        if not rows:
            print("資料庫中尚無案件。請先執行: python scripts/cli.py scrape")
            return 0

        print(f"=== 最近 {len(rows)} 筆案件 ===\n")
        for i, t in enumerate(rows, 1):
            d = t.to_dict()
            print(f"[{i}] {d['tender_name'][:60]}")
            print(f"    案號: {d['tender_id']}")
            print(f"    機關: {d['org_name'] or 'N/A'}")
            print(f"    承辦: {d['contact_person'] or 'N/A'}  電話: {d['phone'] or 'N/A'}")
            print(f"    預算: {d['budget'] or '未公告'}  狀態: {d['status']}")
            print(f"    追蹤: {'是' if d['is_tracked'] else '否'}  建立: {d['created_at']}")
            if d["tender_url"]:
                print(f"    連結: {d['tender_url']}")
            print()
    finally:
        db.close()
    return 0


def cmd_export(args):
    from models import SessionLocal, Tender
    from sqlalchemy import desc

    out = Path(args.output)
    db = SessionLocal()
    try:
        rows = db.query(Tender).order_by(desc(Tender.created_at)).all()
        with out.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "案號", "案名", "招標機關", "承辦人", "電話", "預算金額",
                "狀態", "連結", "是否追蹤", "備註", "爬取時間", "建立時間",
            ])
            for t in rows:
                d = t.to_dict()
                w.writerow([
                    d["tender_id"], d["tender_name"], d["org_name"],
                    d["contact_person"], d["phone"], d["budget"],
                    d["status"], d["tender_url"],
                    "是" if d["is_tracked"] else "否",
                    d["track_note"], d["scraped_at"], d["created_at"],
                ])
        print(f"已匯出 {len(rows)} 筆 → {out.resolve()}")
    finally:
        db.close()
    return 0


def cmd_track(args):
    from models import SessionLocal, Tender

    db = SessionLocal()
    try:
        t = db.query(Tender).filter_by(tender_id=args.tender_id).first()
        if not t:
            print(f"找不到案號: {args.tender_id}")
            return 1
        t.is_tracked = args.on
        t.updated_at = datetime.now()
        db.commit()
        print(f"案號 {args.tender_id} → 追蹤: {'開啟' if args.on else '關閉'}")
    finally:
        db.close()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="政府採購爬蟲 — 命令列測試（不需瀏覽器）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="建立資料庫資料表").set_defaults(func=cmd_init_db)
    sub.add_parser("status", help="顯示設定與資料庫摘要").set_defaults(func=cmd_status)
    sub.add_parser("test-discord", help="發送 Discord 測試通知").set_defaults(func=cmd_test_discord)

    p_preview = sub.add_parser("notify-preview", help="將資料庫最近案件推送到 DC 預覽排版")
    p_preview.add_argument("--limit", type=int, default=5)
    p_preview.set_defaults(func=cmd_notify_preview)

    sub.add_parser("check-network", help="檢測能否連上政府採購網").set_defaults(
        func=cmd_check_network
    )

    p_scrape = sub.add_parser("scrape", help="執行一次公開徵求爬蟲")
    p_scrape.add_argument("--no-filter", action="store_true", help="略過關鍵字篩選（除錯用）")
    p_scrape.add_argument("--force", action="store_true", help="略過連線預檢")
    p_scrape.set_defaults(func=cmd_scrape)

    p_bid = sub.add_parser("scrape-bidding", help="執行一次公開招標爬蟲")
    p_bid.add_argument("--no-filter", action="store_true", help="略過關鍵字篩選")
    p_bid.add_argument("--force", action="store_true", help="略過連線預檢")
    p_bid.set_defaults(func=cmd_scrape_bidding)

    sub.add_parser("repair-phones", help="修正資料庫異常電話（徵求+招標，不需爬蟲）").set_defaults(
        func=cmd_repair_phones
    )

    sub.add_parser("enrich", help="補抓公開徵求承辦人/電話").set_defaults(func=cmd_enrich)
    sub.add_parser("enrich-bidding", help="補抓公開招標承辦人/電話").set_defaults(func=cmd_enrich_bidding)
    sub.add_parser("check-tracked", help="檢查追蹤案件狀態").set_defaults(func=cmd_check_tracked)

    p_list = sub.add_parser("list", help="列出公開徵求案件")
    p_list.add_argument("--limit", type=int, default=10)
    p_list.set_defaults(func=cmd_list)

    p_list_b = sub.add_parser("list-bidding", help="列出公開招標案件")
    p_list_b.add_argument("--limit", type=int, default=10)
    p_list_b.set_defaults(func=cmd_list_bidding)

    p_exp = sub.add_parser("export", help="匯出 CSV")
    p_exp.add_argument("-o", "--output", default="tenders_export.csv")
    p_exp.set_defaults(func=cmd_export)

    p_track = sub.add_parser("track", help="設定追蹤（依案號）")
    p_track.add_argument("tender_id", help="案號")
    p_track.add_argument("--on", action="store_true", default=True)
    p_track.add_argument("--off", action="store_true")
    p_track.set_defaults(func=lambda a: cmd_track(
        argparse.Namespace(tender_id=a.tender_id, on=not a.off)
    ))

    args = parser.parse_args()

    # 除 test-discord 外，自動建立資料表（與 run.py 相同）
    if args.command not in ("test-discord", "check-network"):
        ensure_db()

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
