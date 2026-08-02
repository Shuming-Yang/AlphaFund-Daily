"""規則初評分（ADR-0003）：以程式規則對全體目標基金計算分數，作為完整排名依據。

輸入：M1 `nav.json` 之期間報酬（navValue5..10）與新聞聲量。
維度：
- 績效動能（0–85）：期間報酬加權，映射 30 + 動能% × 1.5。
- 新聞聲量（0–10）：近 7 日基金特定相關新聞數（權重低，每則 +2、5 則封頂）。
評分刻意透明、可測試；前段基金之最終分數以 LLM 深度分析為準（40/40/20）。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import TIMEZONE
from .models import Fund, NewsItem
from .news import fund_matches_title

# navValue5..10 對應期間權重（1M/3M/6M/1Y/2Y/3Y；1Y 與 6M 為主）
PERIOD_WEIGHTS: dict[str, float] = {
    "navValue5": 0.15,  # 1 月
    "navValue6": 0.25,  # 3 月
    "navValue7": 0.25,  # 6 月
    "navValue8": 0.35,  # 1 年
}

# 新聞聲量權重（低）：佔比上限 ~10%（動能 85 + 新聞 10）
NEWS_SCORE_CAP = 10.0      # 新聞聲量分上限（0–10）
NEWS_SCORE_PER_ITEM = 2.0  # 每則基金特定新聞加分

_NON_NUM = re.compile(r"[^\d.\-+]")


def parse_return(value: str | None) -> float | None:
    """解析 TDCC 報酬率字串（%、-、N/A → None）。"""
    if not value:
        return None
    s = _NON_NUM.sub("", value)
    if not s or s in {"-", "N/A", "NA"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def momentum(fund: Fund) -> tuple[float | None, dict[str, float | None]]:
    """加權期間報酬（%）。"""
    parts: dict[str, float | None] = {}
    total_w = 0.0
    acc = 0.0
    for key, w in PERIOD_WEIGHTS.items():
        v = parse_return(fund.returns.get(key, ""))
        parts[key] = v
        if v is not None:
            acc += v * w
            total_w += w
    if total_w == 0:
        return None, parts
    return acc / total_w, parts


def news_volume(fund: Fund, news: list[NewsItem], days: int = 7) -> int:
    """近 N 日與基金**特定**相關的新聞數（WP3：基金特定匹配，消除跨基金污染）。"""
    if not news:
        return 0
    cutoff = datetime.now(ZoneInfo(TIMEZONE)) - timedelta(days=days)
    count = 0
    for item in news:
        if not item.title:
            continue
        if not fund_matches_title(fund, item.title):
            continue
        if item.published_at:
            try:
                dt = datetime.strptime(item.published_at, "%a, %d %b %Y %H:%M:%S %Z")
                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                if dt < cutoff:
                    continue
            except ValueError:
                pass
        count += 1
    return count


def strategy_from_signals(fund: Fund) -> str:
    """依期間報酬規則判定購入模式（規則覆寫，保證分化；ADR-0003 兩階段精神）。

    - 1 月報酬 ≥ 10% → 分批單筆（短期急漲，分批進場避免追高）。
    - 1 年報酬 < 0 → 觀望。
    - 其餘 → 定期定額（長期累積）。
    """
    r = fund.returns
    m1 = parse_return(r.get("navValue5"))
    y1 = parse_return(r.get("navValue8"))
    if m1 is not None and m1 >= 10.0:
        return "分批單筆"
    if y1 is not None and y1 < 0:
        return "觀望"
    return "定期定額"


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def preliminary_score(fund: Fund, news: list[NewsItem]) -> tuple[float, dict[str, float]]:
    """計算初評分與細項。"""
    mom, parts = momentum(fund)
    if mom is None:
        score_m = 30.0
    else:
        # 動能映射：±25% 動能 → ±30 分（基準 30）；上限 90，高動能仍具鑑別度
        score_m = _clamp(30.0 + mom * 1.2, 0.0, 90.0)

    n = news_volume(fund, news)
    score_n = min(NEWS_SCORE_CAP, n * NEWS_SCORE_PER_ITEM)

    total = round(score_m + score_n, 1)
    breakdown = {
        "momentum_score": round(score_m, 2),
        "news_score": round(score_n, 2),
        "momentum_pct": round(mom, 4) if mom is not None else 0.0,
        "news_count": float(n),
    }
    return total, breakdown

