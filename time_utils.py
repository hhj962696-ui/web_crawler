"""
台北時區時間工具
"""

from datetime import datetime
from zoneinfo import ZoneInfo

TZ_TAIPEI = ZoneInfo("Asia/Taipei")


def now_tw() -> datetime:
    """目前台北時間（aware）"""
    return datetime.now(TZ_TAIPEI)


def to_tw(dt: datetime | None) -> datetime | None:
    """將 naive 或 aware datetime 轉為台北時間"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ_TAIPEI)
    return dt.astimezone(TZ_TAIPEI)


def format_tw(dt: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """顯示用台北時間字串"""
    tw = to_tw(dt)
    return tw.strftime(fmt) if tw else ""


def discord_timestamp(dt: datetime | None) -> str:
    """Discord Embed timestamp（ISO8601 +08:00）"""
    tw = to_tw(dt)
    return tw.isoformat(timespec="seconds") if tw else ""
