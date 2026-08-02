"""新聞抓取：Google News RSS（依基金關鍵字查詢）。

說明：台媒自有 RSS 大多不穩定（工商時報 403、經濟日報/中央社無效），
改以 Google News RSS 為主要來源 — 它涵蓋鉅亨網、經濟日報等台媒
與國際媒體，且免費、無需 API key（Q2 決策之務實調整）。

WP3 品質改善（ADR-0011）：
- 抓取改「雙查詢」：基金特定關鍵字（`fund_keyword`，distinctive 標的）＋
  系列關鍵字（`series_keyword`），提升基金特定新聞召回。
- 低訊號過濾（`is_low_signal`）：排除 總覽/淨值/例行公告 等導流頁與黑名單來源。
- 匹配（`fund_matches_title` / `fund_matches_series`）供計分與新聞摘要分層使用。
"""
from __future__ import annotations

import logging
import re
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

_CURRENCIES = (
    "美元|日圓|日幣|人民幣|澳幣|歐元|英鎊|新臺幣|台幣|新加坡幣|港幣|加幣"
    "|瑞士法郎|瑞典幣|紐西蘭幣|南非幣"
)
# 幣別之後可能出現的級別/配息等尾綴（不含「基金」等主詞，避免誤刪「美元基金」）
_CLASS_WORDS = "級別|類股|類別|類|股|累積|月配|季配|年配|穩定|配息|型|acc|dis|Acc|Dis"

# 低訊號標題樣式（導流/例行公告/討論牆等）
_LOW_SIGNAL_TITLE = re.compile(
    r"總覽|淨值|基金老司機|爆料同學會|召開.*股東常會|新增上架|接受.*申購|"
    r"買賣訊號|討論牆|盤中速報|的總覽|報酬與風險|基金資訊"
)
# 黑名單來源（低品質/導流）
_LOW_SIGNAL_SOURCE = re.compile(r"ezfunds\.com\.tw|TAROBO|股市爆料")
_AD_TITLE = re.compile(r"線上基金交易平台|全台最大")


def _build_url(keyword: str) -> str:
    q = urllib.parse.quote(keyword)
    return (
        f"{GOOGLE_NEWS_BASE}?q={q}&hl={GOOGLE_NEWS_LANG}&gl={GOOGLE_NEWS_REGION}"
        f"&ceid={GOOGLE_NEWS_CEID}"
    )


def fund_stem(name: str) -> str:
    """基金名稱正規化：去括號（含未閉合）、去尾綴幣別/級別、壓縮空白。

    例：『瀚亞投資-日本動力股票基金A (美元避險)』→『瀚亞投資-日本動力股票基金』。
    """
    if not name:
        return ""
    s = re.sub(r"[（(][^）)]*[）)]", "", name)  # 完整括號
    s = re.sub(r"[（(][^）)]*$", "", s)          # 未閉合括號
    # 反覆剝離尾端「級別/幣別」型 token（累積/月配/級別/A 等），直至穩定
    while True:
        prev = s
        s = re.sub(rf"\s*(?:{_CURRENCIES})\s*(?:避險|對沖)?\s*$", "", s)
        s = re.sub(r"\s*[-－]?[A-Za-z0-9]+\s*(?:級別|累積|月配|季配|年配|配息|類|股|acc|dis|型)?\s*$", "", s)
        s = re.sub(rf"\s*(?:{_CLASS_WORDS})\s*$", "", s)
        s = re.sub(r"\s*[-－]\s*$", "", s)
        if s == prev:
            break
    s = re.sub(r"\s+", "", s)
    return s.strip(" -－")


def fund_distinctive(name: str) -> str:
    """基金特定識別字：連字號後段標的（最小清洗，保留級別殘餘以利標題匹配）。

    例：『聯博-國際科技基金S級別美元』→『國際科技基金』；
        『霸菱韓國基金-A類美元累積型』→『霸菱韓國基金』（後段全為級別時退回前段）。
    """
    st = fund_stem(name)
    parts = re.split(r"[－\-]", st, maxsplit=1)
    if len(parts) == 2:
        cand = parts[1].strip()
        # 後段只剩級別資訊（無中文標的）→ 退回前段
        if len(cand) >= 4 and re.search(r"[\u4e00-\u9fff]", cand):
            return cand
        return parts[0].strip()
    return st


def series_keyword(fund: Fund) -> str:
    """系列主名稱關鍵字（抓取端召回用）。"""
    name = fund.name or ""
    parts = re.split(r"[－\-]", name, maxsplit=1)
    core = parts[0].strip() if len(parts) == 2 else name.strip()
    return core[:50]


def fund_keyword(fund: Fund) -> str:
    """基金特定查詢關鍵字（WP3：distinctive 標的，取代廣義系列名）。"""
    name = fund.name or ""
    d = fund_distinctive(name)
    if len(d) >= 4 and re.search(r"[\u4e00-\u9fff]", d):
        return d[:50]
    return series_keyword(fund)


def is_low_signal(item: NewsItem) -> bool:
    """低訊號新聞：導流/例行公告/黑名單來源/平台廣告。"""
    title = item.title or ""
    source = item.source or ""
    return bool(
        _LOW_SIGNAL_TITLE.search(title)
        or _LOW_SIGNAL_SOURCE.search(source)
        or _AD_TITLE.search(title)
    )


def fund_matches_title(fund: Fund, title: str) -> bool:
    """基金特定匹配：distinctive 標的或全名出現在標題（計分與摘要首選）。"""
    if not title:
        return False
    d = fund_distinctive(fund.name or "")
    if d and d in title:
        return True
    return bool(fund.name and fund.name in title)


def fund_matches_series(fund: Fund, title: str) -> bool:
    """系列層匹配（摘要 fallback 用）。"""
    if not title:
        return False
    core = series_keyword(fund)
    return bool(core and core in title)


def fetch_google_news(keyword: str, max_items: int = 8) -> list[NewsItem]:
    """以關鍵字查詢 Google News RSS，回傳最近新聞項目（已過濾低訊號）。"""
    if not keyword:
        return []
    resp = httpx.get(
        _build_url(keyword), timeout=20, follow_redirects=True, headers=DEFAULT_HEADERS
    )
    resp.raise_for_status()
    feed = parse(resp.content)
    items: list[NewsItem] = []
    for e in feed.entries[:max_items]:
        item = NewsItem(
            title=(e.get("title") or "").strip(),
            url=e.get("link") or "",
            source=((e.get("source") or {}).get("title") or "").strip(),
            published_at=e.get("published") or "",
            summary=((e.get("summary") or "").strip()),
            keywords=[keyword],
        )
        if not is_low_signal(item):
            items.append(item)
    return items


def _normalize_title(title: str) -> str:
    """正規化標題：小寫、去除標點與空白（供事件去重）。"""
    return "".join(ch.lower() for ch in title if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def fetch_universe_news(
    funds: list[Fund],
    limit: int | None = None,
    max_per_fund: int = 5,
    delay: float = 0.5,
) -> list[NewsItem]:
    """對基金清單逐一「雙查詢」（基金特定 + 系列）Google News，合併去重。

    - 基金特定關鍵字查詢：聚焦標的本身，提升精準度。
    - 系列關鍵字查詢：補召回（市場/主題新聞），同系列僅查一次。
    - 低訊號項目於 `fetch_google_news` 已過濾；再依 (title, url) 去重。
    """
    targets = funds[:limit] if limit is not None else funds
    seen_items: set[str] = set()
    seen_specific: set[str] = set()
    seen_series: set[str] = set()
    out: list[NewsItem] = []

    for fund in targets:
        keywords: list[str] = []
        kw_specific = fund_keyword(fund)
        if kw_specific and kw_specific not in seen_specific:
            seen_specific.add(kw_specific)
            keywords.append(kw_specific)
        kw_series = series_keyword(fund)
        if kw_series and kw_series not in seen_series:
            seen_series.add(kw_series)
            keywords.append(kw_series)

        for kw in keywords:
            try:
                items = fetch_google_news(kw, max_per_fund)
            except Exception as exc:  # noqa: BLE001 — 單一關鍵字失敗不中斷
                logger.warning("Google News 查詢失敗: %s (%s)", kw, exc)
                continue
            for it in items:
                # 事件去重：以正規化標題為 key（同事件跨媒體合併）
                key = _normalize_title(it.title)
                if not key or key in seen_items:
                    continue
                seen_items.add(key)
                out.append(it)
            time.sleep(delay)

    return out
