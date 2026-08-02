"""規則初評分（ADR-0003 / ADR-0012）：以程式規則對全體目標基金計算分數，作為完整排名依據。

投資模式（預設「長期投資 + 被動收入」），評分導向：穩定 > 高獲利、穩定持續 > 短期暴衝、穩定成長 > 高波動。
- 成長品質（0–35）：長期報酬（6M/1Y/2Y/3Y 加權）並報酬遞減，避免高獲利碾壓穩定型。
- 穩定持續（0–35）：長期正報酬持續、無深回撤、近期未急跌。
- 收入加分（0–10）：依近 12M 配息率分級（被動收入導向）。
- 新聞聲量（0–10）：近 7 日基金特定相關新聞數（權重低）。
- 風險調整（−8~+3）：依 TDCC 風險報酬等級 RR（高風險不適合長期投資）。
- 槓桿懲罰（−15）：名稱含槓桿/放空/反向等工具（貨幣避險「對沖/Hedged」不算）。
評分刻意透明、可測試；前段基金之最終分數以 LLM 深度分析為準（40/40/20）。
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import (
    GROWTH_DECAY,
    GROWTH_MAX,
    GROWTH_WEIGHTS,
    INCOME_BONUS,
    INCOME_BONUS_COMPLETE_FLOOR,
    INCOME_BONUS_MISSING_FLOOR,
    INCOME_BONUS_NO_DATA_FLOOR,
    INCOME_BONUS_PRINCIPAL_FLOOR,
    INCOME_YIELD_PER_POINT,
    LEVERAGE_PENALTY,
    RISK_BONUS_RR,
    STABILITY_MAX_NEW,
    TIMEZONE,
)
from .models import Fund, NewsItem
from .news import fund_matches_title

# 新聞聲量權重（低）：佔比上限 10（穩定 35 + 成長 35 + 收入 10 為主）
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

# 槓桿/放空/反向工具（非貨幣避險「對沖/Hedged/避險」）
_LEVERAGE_RE = re.compile(
    r"槓桿|放空|反向|Inverse|Leveraged|Daily\s*\d+[xX]|\b\d+[xX]\b",
    re.IGNORECASE,
)

_NON_NUM = re.compile(r"[^\d.\-+]")

# 期間報酬順序（navValue5..10 = 1M/3M/6M/1Y/2Y/3Y）
_PERIOD_KEYS = ("navValue5", "navValue6", "navValue7", "navValue8", "navValue9", "navValue10")


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
    """期間正報酬比例（0–1）：期間報酬中為正值之比例（簡易穩定指標）。"""
    values = [
        parse_return(fund.returns.get(k, "")) for k in _PERIOD_KEYS
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


# 舊動能期間權重（含 1M/3M）保留：供新聞目標排序等用途
PERIOD_WEIGHTS: dict[str, float] = {
    "navValue5": 0.05,   # 1 月
    "navValue6": 0.10,   # 3 月
    "navValue7": 0.20,   # 6 月
    "navValue8": 0.30,   # 1 年
    "navValue9": 0.20,   # 2 年
    "navValue10": 0.15,  # 3 年
}


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


def long_term_return(fund: Fund) -> float | None:
    """長期加權報酬（%）：6M/1Y/2Y/3Y，不含短線 1M/3M。"""
    total_w = 0.0
    acc = 0.0
    for key, w in GROWTH_WEIGHTS.items():
        v = parse_return(fund.returns.get(key, ""))
        if v is not None:
            acc += v * w
            total_w += w
    if total_w == 0:
        return None
    return acc / total_w


def growth_score(fund: Fund) -> tuple[float, float | None]:
    """成長品質分（0–GROWTH_MAX）：長期報酬，報酬遞減（exp）。

    高獲利報酬遞減 → 穩定型有機會靠穩定性逆轉（穩定獲利 > 高獲利）。
    回傳 (分數, 長期報酬%)。
    """
    lt = long_term_return(fund)
    if lt is None:
        return 0.0, None
    if lt <= 0:
        return 0.0, lt
    score = GROWTH_MAX * (1 - math.exp(-lt / GROWTH_DECAY))
    return round(score, 2), lt


def stability_persistence(fund: Fund) -> tuple[float, dict[str, float]]:
    """穩定持續分（0–STABILITY_MAX_NEW）。

    - 長期持續正報酬（0–15）：1Y/2Y/3Y 各正 +5（穩定持續獲利）。
    - 無深回撤（0–12）：最差單期分層（穩定成長 > 高波動）。
    - 近期未急跌（0–8）：1M/3M 未重挫。
    回傳 (分數, 細項)。
    """
    v = [parse_return(fund.returns.get(k, "")) for k in _PERIOD_KEYS]
    if any(x is None for x in v):
        return 0.0, {"pos_long": 0.0, "drawdown": 0.0, "recent": 0.0}
    vf: list[float] = [x for x in v if x is not None]  # type: ignore[misc]

    cont = sum(5.0 for i in (3, 4, 5) if vf[i] > 0)  # 1Y/2Y/3Y

    worst = min(vf)
    if worst >= 5:
        draw = 12.0
    elif worst >= 0:
        draw = 9.0
    elif worst >= -5:
        draw = 6.0
    elif worst >= -15:
        draw = 2.0
    else:
        draw = 0.0

    if vf[0] > -3 and vf[1] > -5:
        rec = 8.0
    elif vf[0] > -8 and vf[1] > -10:
        rec = 5.0
    elif vf[0] > -15:
        rec = 2.0
    else:
        rec = 0.0

    total = round(min(STABILITY_MAX_NEW, cont + draw + rec), 1)
    return total, {"pos_long": cont, "drawdown": draw, "recent": rec}


def is_leveraged_name(name: str) -> bool:
    """名稱是否為槓桿/放空/反向工具（不含貨幣避險「對沖/Hedged」）。"""
    return bool(name and _LEVERAGE_RE.search(name))


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
    """收入加分（0–INCOME_BONUS）：依有效配息率分級 + 四級保底。

    有效配息率 = 名目配息率 × 收益品質（本金配息打折）。
    保底層級（資料完整度/收益品質）：
    - 無配息資料（配息型）→ NO_DATA_FLOOR；非配息型 → 0。
    - 資料齊全且非全本金 → COMPLETE_FLOOR。
    - 資料齊全且全本金 → PRINCIPAL_FLOOR。
    - 有配息但缺比例資料 → MISSING_FLOOR。
    回傳 (加分, 有效配息率%)。
    """
    if not fund.dividends:
        return (INCOME_BONUS_NO_DATA_FLOOR if income_cls == "配息型" else 0.0), None

    eff = fund.effective_yield()
    quality = fund.income_quality()
    all_ratio = all(d.income_ratio is not None for d in fund.dividends)

    if all_ratio and quality <= 1e-9:
        floor = INCOME_BONUS_PRINCIPAL_FLOOR      # 真本金
    elif all_ratio:
        floor = INCOME_BONUS_COMPLETE_FLOOR       # 完整
    else:
        floor = INCOME_BONUS_MISSING_FLOOR        # 折半（缺比例資料）

    if eff is not None and eff > 0:
        scaled = min(INCOME_BONUS, eff * INCOME_YIELD_PER_POINT)
        return round(max(scaled, floor), 1), eff
    return floor, eff  # 有效收益為 0（全本金）→ 保底


def preliminary_score(fund: Fund, news: list[NewsItem]) -> tuple[float, dict[str, float]]:
    """計算初評分與細項（穩定導向）。

    score = 成長品質 + 穩定持續 + 收入 + 新聞 + 風險調整(RR) + 槓桿懲罰。
    """
    g, lt = growth_score(fund)
    s, stab_detail = stability_persistence(fund)

    n = news_volume(fund, news)
    score_n = min(NEWS_SCORE_CAP, n * NEWS_SCORE_PER_ITEM)

    income_cls = income_class_from_name(fund.name)
    income_bonus, yield_pct = income_bonus_from_yield(fund, income_cls)

    risk_bonus = RISK_BONUS_RR.get(fund.risk_level or "", 0.0)
    lev_penalty = -LEVERAGE_PENALTY if is_leveraged_name(fund.name) else 0.0

    raw_yield = fund.annualized_yield() if fund.dividends else None
    total = round(_clamp(g + s + score_n + income_bonus + risk_bonus + lev_penalty, 0.0, 100.0), 1)
    breakdown = {
        "growth_score": round(g, 2),
        "stability_score": round(s, 1),
        "pos_long": round(stab_detail["pos_long"], 1),
        "drawdown": round(stab_detail["drawdown"], 1),
        "recent": round(stab_detail["recent"], 1),
        "news_score": round(score_n, 2),
        "income_bonus": round(income_bonus, 1),
        "risk_bonus": round(risk_bonus, 1),
        "leverage_penalty": round(lev_penalty, 1),
        "risk_level": fund.risk_level or "",
        "asset_class": fund.asset_class or "",
        "income_class": income_cls,
        "yield_pct": round(raw_yield, 2) if raw_yield is not None else 0.0,
        "effective_yield_pct": round(yield_pct, 2) if yield_pct is not None else 0.0,
        "income_quality": round(fund.income_quality(), 3),
        "long_term_return": round(lt, 4) if lt is not None else 0.0,
        "news_count": float(n),
    }
    return total, breakdown

