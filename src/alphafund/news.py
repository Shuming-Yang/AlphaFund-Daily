"""新聞抓取：Google News RSS（依基金關鍵字查詢）。

說明：台媒自有 RSS 大多不穩定（工商時報 403、經濟日報/中央社無效），
改以 Google News RSS 為主要來源 — 它涵蓋鉅亨網、經濟日報等台媒
與國際媒體，且免費、無需 API key（Q2 決策之務實調整）。
"""
from __future__ import annotations

import logging
import time
import urllib.parse

import httpx
from feedparser import parse

from .config import (
    DEFAULT_HEADERS,
    GOOGLE_NEWS_BASE,
    GOOGLE_NEWS_CEID,
    GOOGLE_NEWS_LANG,
    GOOGLE_NEWS_REGION,
)
from .models import Fund, NewsItem

logger = logging.getLogger(__name__)


def _build_url(keyword: str) -> str:
    q = urllib.parse.quote(keyword)
    return (
        f"{GOOGLE_NEWS_BASE}?q={q}&hl={GOOGLE_NEWS_LANG}&gl={GOOGLE_NEWS_REGION}"
        f"&ceid={GOOGLE_NEWS_CEID}"
    )


def fund_keyword(fund: Fund) -> str:
    """由基金名稱產生查詢關鍵字：取『-』前的系列/主名稱並截短。"""
    name = fund.name or ""
    core = name.split("-")[0].strip()
    if not core:
        core = name.strip()
    return core[:50]


def fetch_google_news(keyword: str, max_items: int = 8) -> list[NewsItem]:
    """以關鍵字查詢 Google News RSS，回傳最近新聞項目。"""
    if not keyword:
        return []
    resp = httpx.get(
        _build_url(keyword), timeout=20, follow_redirects=True, headers=DEFAULT_HEADERS
    )
    resp.raise_for_status()
    feed = parse(resp.content)
    items: list[NewsItem] = []
    for e in feed.entries[:max_items]:
        items.append(
            NewsItem(
                title=(e.get("title") or "").strip(),
                url=e.get("link") or "",
                source=((e.get("source") or {}).get("title") or "").strip(),
                published_at=e.get("published") or "",
                summary=((e.get("summary") or "").strip()),
            )
        )
    return items


def fetch_universe_news(
    funds: list[Fund],
    limit: int | None = None,
    max_per_fund: int = 5,
    delay: float = 0.5,
) -> list[NewsItem]:
    """對基金清單逐一查詢 Google News，合併去重。"""
    targets = funds[:limit] if limit is not None else funds
    seen_items: set[tuple[str, str]] = set()
    seen_keywords: set[str] = set()
    out: list[NewsItem] = []

    for fund in targets:
        kw = fund_keyword(fund)
        if kw in seen_keywords:
            continue
        seen_keywords.add(kw)
        try:
            items = fetch_google_news(kw, max_per_fund)
        except Exception as exc:  # noqa: BLE001 — 單一基金失敗不中斷
            logger.warning("Google News 查詢失敗: %s (%s)", kw, exc)
            continue
        for it in items:
            key = (it.title, it.url)
            if key in seen_items:
                continue
            seen_items.add(key)
            out.append(it)
        time.sleep(delay)

    return out
