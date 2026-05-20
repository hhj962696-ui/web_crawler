"""
Discord Webhook 通知模組
支援 Embed 卡片格式、多訊息拆分、狀態變更通知
"""

import logging
import time
import requests
from typing import Optional

from config import config

logger = logging.getLogger(__name__)

# 預算金額對應的 Embed 顏色（十進位）
COLOR_HIGH = 0xE74C3C      # 紅色 — 1000萬以上
COLOR_MEDIUM = 0xF39C12    # 橘色 — 100萬~1000萬
COLOR_LOW = 0x2ECC71       # 綠色 — 100萬以下
COLOR_UNKNOWN = 0x3498DB   # 藍色 — 金額未知
COLOR_STATUS = 0x9B59B6    # 紫色 — 狀態變更
COLOR_ERROR = 0xE74C3C     # 紅色 — 錯誤通知
COLOR_INFO = 0x1ABC9C      # 青色 — 一般資訊


def _parse_budget_value(budget_str: str) -> Optional[float]:
    """解析預算金額字串為數值"""
    if not budget_str:
        return None
    try:
        cleaned = budget_str.replace(",", "").replace("元", "").replace("$", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _get_budget_color(budget_str: str) -> int:
    """根據預算金額返回對應顏色"""
    value = _parse_budget_value(budget_str)
    if value is None:
        return COLOR_UNKNOWN
    if value >= 10_000_000:
        return COLOR_HIGH
    if value >= 1_000_000:
        return COLOR_MEDIUM
    return COLOR_LOW


def _build_tender_embed(tender: dict) -> dict:
    """建構單一案件的 Embed 物件"""
    budget_display = tender.get("budget", "未公告") or "未公告"
    color = _get_budget_color(budget_display)

    embed = {
        "title": f"📋 {tender.get('tender_name', '未命名案件')[:200]}",
        "color": color,
        "fields": [
            {
                "name": "📌 案號",
                "value": tender.get("tender_id", "N/A"),
                "inline": True,
            },
            {
                "name": "🏢 招標機關",
                "value": tender.get("org_name", "N/A") or "N/A",
                "inline": True,
            },
            {
                "name": "👤 承辦人",
                "value": tender.get("contact_person", "N/A") or "N/A",
                "inline": True,
            },
            {
                "name": "📞 電話",
                "value": tender.get("phone", "N/A") or "N/A",
                "inline": True,
            },
            {
                "name": "💰 預算金額",
                "value": budget_display,
                "inline": True,
            },
        ],
    }

    scraped_at = tender.get("scraped_at", "")
    if scraped_at:
        embed["timestamp"] = scraped_at

    # 加入連結
    url = tender.get("tender_url", "")
    if url:
        embed["url"] = url

    return embed


def send_new_tenders_notification(tenders: list[dict]) -> bool:
    """
    發送新案件通知到 Discord
    每則訊息最多 5 個 Embed，超過則拆分
    """
    webhook_url = config.DISCORD_WEBHOOK_URL
    if not webhook_url:
        logger.warning("Discord Webhook URL 未設定，跳過通知")
        return False

    if not tenders:
        logger.info("沒有新案件需要通知")
        return True

    total = len(tenders)
    batch_size = config.DISCORD_EMBED_BATCH_SIZE
    success = True

    for i in range(0, total, batch_size):
        batch = tenders[i:i + batch_size]
        embeds = [_build_tender_embed(t) for t in batch]

        page_info = f"（{i // batch_size + 1}/{(total - 1) // batch_size + 1}）" if total > batch_size else ""

        payload = {
            "content": f"🆕 **公開徵求新案通知** — 共 {total} 筆 {page_info}",
            "embeds": embeds,
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            if resp.status_code == 204:
                logger.info(f"Discord 通知已發送：第 {i + 1}~{min(i + batch_size, total)} 筆")
            elif resp.status_code == 429:
                # Rate limited
                retry_after = resp.json().get("retry_after", 5)
                logger.warning(f"Discord rate limited，等待 {retry_after} 秒後重試")
                time.sleep(retry_after)
                resp = requests.post(webhook_url, json=payload, timeout=10)
            else:
                logger.error(f"Discord 通知失敗: {resp.status_code} - {resp.text}")
                success = False
        except requests.RequestException as e:
            logger.error(f"Discord 通知發送異常: {e}")
            success = False

        # 批次之間延遲，避免觸發 rate limit
        if i + batch_size < total:
            time.sleep(1.5)

    return success


def send_status_change_notification(tender: dict, old_status: str, new_status: str) -> bool:
    """發送追蹤案件狀態變更通知"""
    webhook_url = config.DISCORD_WEBHOOK_URL
    if not webhook_url:
        return False

    embed = {
        "title": f"🔄 追蹤案件狀態變更",
        "color": COLOR_STATUS,
        "description": f"**{tender.get('tender_name', '未命名')[:200]}**",
        "fields": [
            {
                "name": "📌 案號",
                "value": tender.get("tender_id", "N/A"),
                "inline": True,
            },
            {
                "name": "⬅️ 舊狀態",
                "value": old_status or "N/A",
                "inline": True,
            },
            {
                "name": "➡️ 新狀態",
                "value": new_status or "N/A",
                "inline": True,
            },
            {
                "name": "🏢 招標機關",
                "value": tender.get("org_name", "N/A") or "N/A",
                "inline": True,
            },
            {
                "name": "💰 預算金額",
                "value": tender.get("budget", "未公告") or "未公告",
                "inline": True,
            },
        ],
    }

    url = tender.get("tender_url", "")
    if url:
        embed["url"] = url

    payload = {
        "content": "📢 **您追蹤的案件狀態已更新！**",
        "embeds": [embed],
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 204:
            logger.info(f"狀態變更通知已發送：{tender.get('tender_id')}")
            return True
        else:
            logger.error(f"狀態變更通知失敗: {resp.status_code}")
            return False
    except requests.RequestException as e:
        logger.error(f"狀態變更通知異常: {e}")
        return False


def send_error_notification(error_msg: str) -> bool:
    """發送爬蟲錯誤通知"""
    webhook_url = config.DISCORD_WEBHOOK_URL
    if not webhook_url:
        return False

    embed = {
        "title": "❌ 爬蟲執行錯誤",
        "color": COLOR_ERROR,
        "description": f"```\n{error_msg[:1500]}\n```",
        "fields": [
            {
                "name": "⏰ 發生時間",
                "value": time.strftime("%Y-%m-%d %H:%M:%S"),
                "inline": True,
            }
        ],
    }

    payload = {
        "content": "⚠️ **爬蟲系統異常通知**",
        "embeds": [embed],
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        return resp.status_code == 204
    except requests.RequestException:
        return False


def send_test_notification() -> bool:
    """發送測試通知（用於驗證 Webhook 設定）"""
    webhook_url = config.DISCORD_WEBHOOK_URL
    if not webhook_url:
        return False

    embed = {
        "title": "✅ Webhook 測試成功",
        "color": COLOR_INFO,
        "description": "政府採購爬蟲系統 Discord 通知功能正常運作！",
        "fields": [
            {
                "name": "⏰ 測試時間",
                "value": time.strftime("%Y-%m-%d %H:%M:%S"),
                "inline": True,
            },
            {
                "name": "🔑 篩選關鍵字",
                "value": ", ".join(config.FILTER_KEYWORDS) or "未設定",
                "inline": False,
            },
        ],
    }

    payload = {
        "content": "🧪 **系統測試通知**",
        "embeds": [embed],
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        return resp.status_code == 204
    except requests.RequestException as e:
        logger.error(f"測試通知發送失敗: {e}")
        return False
