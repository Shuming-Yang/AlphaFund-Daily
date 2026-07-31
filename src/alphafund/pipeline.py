"""M1 資料管道編排：目標基金清單 → 淨值 → 新聞 → 每日快照。"""
from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import CHANNELS, HISTORY_DIR, TIMEZONE, UNIVERSE_FILE
from .filters import filter_funds
from .models import DailySnapshot, Fund, NewsItem
from .news import fetch_universe_news
from .tdcc import TdccClient

logger = logging.getLogger(__name__)


def today_str() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")


def build_universe(client: TdccClient) -> list[Fund]:
    """三通路上架基金 ∩ 允許幣別 → 目標基金清單。"""
    channel_sets: dict[str, set[str]] = {}
    for name, info in CHANNELS.items():
        rows = client.query_org_detail(info["org_code"])
        channel_sets[name] = {str(r["fundCode"]) for r in rows}
        logger.info("%s 上架基金: %d", name, len(channel_sets[name]))
    raw = client.query_all_funds(currency="all")
    logger.info("TDCC 境外基金記錄: %d", len(raw))
    funds = filter_funds(raw, channel_sets)
    logger.info("目標基金清單（通路 ∩ USD）: %d", len(funds))
    return funds


def _write_json_gz(path: Path, data) -> None:
    """以 gzip 壓縮寫入 JSON（歷史檔壓縮後單日約 0.3MB，利於 git 長期留存）。"""
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=2))


def save_snapshot(snapshot: DailySnapshot) -> Path:
    day_dir = HISTORY_DIR / snapshot.date
    day_dir.mkdir(parents=True, exist_ok=True)

    _write_json_gz(day_dir / "snapshot.json.gz", json.loads(snapshot.model_dump_json()))
    _write_json_gz(day_dir / "news.json.gz", [n.model_dump() for n in snapshot.news])
    nav = [
        {
            "fund_code": f.fund_code,
            "name": f.name,
            "currency": f.currency,
            "nav": f.nav,
            "nav_date": f.nav_date,
            "returns": f.returns,
            "channels": f.channels,
        }
        for f in snapshot.funds
    ]
    _write_json_gz(day_dir / "nav.json.gz", nav)
    _write_json_gz(day_dir / "universe.json.gz", [f.model_dump() for f in snapshot.funds])

    # 最新清單保留未壓縮，方便直接讀取
    UNIVERSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    UNIVERSE_FILE.write_text(
        json.dumps([f.model_dump() for f in snapshot.funds], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return day_dir


def run_m1(
    date: str | None = None,
    news_limit: int | None = None,
    save: bool = True,
) -> DailySnapshot:
    """執行完整 M1 管線並回傳快照。"""
    date = date or today_str()
    funds: list[Fund] = []
    news: list[NewsItem] = []
    with TdccClient() as client:
        funds = build_universe(client)
    if news_limit is None or news_limit > 0:
        news = fetch_universe_news(funds, limit=news_limit)
        logger.info("新聞項目: %d", len(news))
    else:
        logger.info("略過新聞抓取")

    snapshot = DailySnapshot(
        date=date, universe_count=len(funds), funds=funds, news=news
    )
    if save:
        path = save_snapshot(snapshot)
        logger.info("快照已寫入: %s", path)
    return snapshot
