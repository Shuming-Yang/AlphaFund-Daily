"""規則初評分（ADR-0003）：以程式規則對全體目標基金計算分數，作為完整排名依據。

投資模式（預設「長期投資 + 被動收入」）：
- 績效動能（0–85）：長期導向期間報酬加權（1M/3M/6M/1Y/2Y/3Y）。
- 新聞聲量（0–10）：近 7 日基金特定相關新聞數（權重低，每則 +2、5 則封頂）。
- 收入加分（0–10）：配息型基金 +10（被動收入導向）。
- 穩定加分（0–5）：期間正報酬比例。
評分刻意透明、可測試；前段基金之最終分數以 LLM 深度分析為準（40/40/20）。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import INCOME_BONUS, INCOME_BONUS_UNKNOWN, INCOME_YIELD_PER_POINT, STABILITY_MAX, TIMEZONE
from .models import Fund, NewsItem
from .news import fund_matches_title

# 長期導向期間權重（1M/3M/6M/1Y/2Y/3Y）：低短期、重長期
PERIOD_WEIGHTS: dict[str, float] = {
    "navValue5": 0.05,   # 1 月
    "navValue6": 0.10,   # 3 月
    "navValue7": 0.20,   # 6 月
    "navValue8": 0.30,   # 1 年
    "navValue9": 0.20,   # 2 年
    "navValue10": 0.15,  # 3 年
}

# 新聞聲量權重（低）：佔比上限 ~10%（動能 85 + 新聞 10）
NEWS_SCORE_CAP = 10.0      # 新聞聲量分上限（0–10）
NEWS_SCORE_PER_ITEM = 2.0  # 每則基金特定新聞加分

# 揭露括號（非級別類型）：含 本基金/Rule 144A/投資等級 之風險揭露，分類前移除
_DISCLOSURE_RE = re.compile(
    r"[（(][^（）()]*?(?:本基金|Rule\s*144A|投資等級)[^（）()]*?[）)]"
)

_INCOME_PAT = re.compile(
    r"配息|Mdis|Dis\)|月配|季配|年配|穩定月配|固定配息|收益"
)
_ACC_PAT = re.compile(r"累積|acc\)|Acc\)|資本成長|增長")

_NON_NUM = re.compile(r"[^\d.\-+]")


def income_class_from_name(name: str) -> str:
    """由基金名稱判斷收益類型（移除揭露括號後）。

    配息型 → "配息型"；累積型 → "累積型"；其餘 → "其他"。
    """
    if not name:
        return "其他"
    cleaned = _DISCLOSURE_RE.sub("", name)
    if _INCOME_PAT.search(cleaned):
        return "配息型"
    if _ACC_PAT.search(cleaned):
        return "累積型"
    return "其他"


def stability_score(fund: Fund) -> float:
    """期間正報酬比例（0–1）：期間報酬中為正值之比例。"""
    values = [
        parse_return(fund.returns.get(k, "")) for k in ("navValue5", "navValue6", "navValue7", "navValue8", "navValue9", "navValue10")
    ]
    values = [v for v in values if v is not None]
    if not values:
        return 0.0
    return sum(1 for v in values if v > 0) / len(values)


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


def income_bonus_from_yield(fund: Fund, income_cls: str) -> tuple[float, float | None]:
    """收入加分（0–10）：依實際近 12M 配息率分級。

    - 有配息率（>0）→ min(上限, 配息率 × INCOME_YIELD_PER_POINT)。
    - 配息型但無配息資料 → 保守底分 INCOME_BONUS_UNKNOWN。
    - 其餘 → 0。
    回傳 (加分, 配息率%)。
    """
    yield_pct = fund.annualized_yield()
    if yield_pct is not None and yield_pct > 0:
        bonus = min(INCOME_BONUS, yield_pct * INCOME_YIELD_PER_POINT)
        return round(bonus, 1), yield_pct
    if income_cls == "配息型":
        return INCOME_BONUS_UNKNOWN, yield_pct
    return 0.0, yield_pct


def preliminary_score(fund: Fund, news: list[NewsItem]) -> tuple[float, dict[str, float]]:
    """計算初評分與細項。"""
    mom, parts = momentum(fund)
    if mom is None:
        score_m = 30.0
    else:
        # 動能映射：±25% 動能 → ±30 分（基準 30）；上限 85，保留收入/穩定加分空間
        score_m = _clamp(30.0 + mom * 1.2, 0.0, 85.0)

    n = news_volume(fund, news)
    score_n = min(NEWS_SCORE_CAP, n * NEWS_SCORE_PER_ITEM)

    income_cls = income_class_from_name(fund.name)
    income_bonus, yield_pct = income_bonus_from_yield(fund, income_cls)
    stab_bonus = round(stability_score(fund) * STABILITY_MAX, 1)

    total = round(_clamp(score_m + score_n + income_bonus + stab_bonus, 0.0, 100.0), 1)
    breakdown = {
        "momentum_score": round(score_m, 2),
        "news_score": round(score_n, 2),
        "income_bonus": round(income_bonus, 1),
        "stability_bonus": round(stab_bonus, 1),
        "income_class": income_cls,
        "yield_pct": round(yield_pct, 2) if yield_pct is not None else 0.0,
        "momentum_pct": round(mom, 4) if mom is not None else 0.0,
        "news_count": float(n),
    }
    return total, breakdown

