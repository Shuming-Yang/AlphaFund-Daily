"""深度分析：Gemini LLM Prompt 與回應解析。

Prompt 依 Q3/構想文件之「資深境外基金與總體經濟分析師」樣板，
輸出為 JSON（評分矩陣 40/40/20、購入模式、優劣勢、評級、免責聲明）。
"""
from __future__ import annotations

import logging
from typing import Any

from .models import DeepAnalysis, Fund, NewsItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是資深境外基金與總體經濟分析師。你專業、客觀，擅長整合市場新聞、
總體經濟趨勢與基金基本面數據，進行精準的基金價值評估與投資策略分析。

規則：
1. 新聞篩選與摘要：過濾與基金標的/產業/區域無關之雜訊，萃取 2–3 點關鍵動態，
   並標示整體情緒為 Positive / Neutral / Negative。
2. 價值評分（0–100，評分矩陣）：
   - 總體經濟與產業風向 (40%)：相關新聞與近期市場趨勢利多程度。
   - 績效與風險表現 (40%)：近期淨值走勢與穩定度。
   - 市場情緒與資金流向 (20%)：新聞與機構聲量傾向。
   評分校準指引：
   - 60 分為「訊號分歧」基準點。
   - 常態分布在 55–85；僅在至少兩個維度同時明確轉佳且無顯著風險時給 >88。
   - 僅在明顯負面訊號（重大風險／績效轉差／情緒偏空）時給 <40。
   - 避免將不同標的都評為相近分數（如一律 80 分）；依實際強度拉開差距。
3. 購入模式：依波動度與趨勢判斷，選 定期定額 / 分批單筆 / 觀望 之一。
4. 優劣勢：提供 2 個主要優勢 (pros) 與 2 個潛在風險 (cons)。
5. 綜合評級：依整體情況選 強力推薦 / 值得關注 / 中立觀望 / 暫時避開 之一。
   評級決策指引：
   - 強力推薦：需至少兩個維度同時明確轉佳，且無顯著風險。
   - 值得關注：具潛力但仍需確認。
   - 中立觀望：訊號分歧或不明確時之預設。
   - 暫時避開：負面訊號明顯、風險偏高。
   - 評級應與價值分數一致：高分（>85）不得配 暫時避開；低分（<55）不得配 強力推薦。
   - 避免過度集中單一評級；依實際強度選用不同評級。
6. 嚴格限制：僅能依據提供的 Input Data 分析，不可編造未提及之數據或新聞背景；
   用語專業、中立、客觀。

請以 JSON 輸出（不要包含任何額外說明文字），結構如下：
{
  "news_summary": ["重點1", "重點2", "重點3"],
  "market_sentiment": "Positive|Neutral|Negative",
  "value_score": 85,
  "score_rationale": "評分理由（簡短）",
  "recommended_strategy": "定期定額|分批單筆|觀望",
  "strategy_explanation": "策略原因（簡短）",
  "pros": ["優勢1", "優勢2"],
  "cons": ["風險1", "風險2"],
  "overall_rating": "強力推薦|值得關注|中立觀望|暫時避開"
}
"""


def _format_returns(fund: Fund) -> str:
    periods = [
        ("1月", "navValue5"),
        ("3月", "navValue6"),
        ("6月", "navValue7"),
        ("1年", "navValue8"),
        ("2年", "navValue9"),
        ("3年", "navValue10"),
    ]
    parts = []
    for label, key in periods:
        v = fund.returns.get(key) or "-"
        parts.append(f"{label}={v}%")
    return "、".join(parts)


def build_user_prompt(fund: Fund, news: list[NewsItem], analysis_date: str) -> str:
    news_lines = "\n".join(f"- [{n.source}] {n.title}（{n.published_at}）" for n in news[:10])
    if not news_lines:
        news_lines = "（無近 24 小時相關新聞）"
    return f"""請分析以下境外基金並輸出 JSON：

## Input Data
- 基金名稱：{fund.name}
- 基金代碼：{fund.fund_code}
- 計價幣別：{fund.currency}
- 銷售通路：{'、'.join(fund.channels) or '-'}
- 最新淨值：{fund.nav}（{fund.nav_date}）
- 期間報酬率：{_format_returns(fund)}
- 分析日期：{analysis_date}

## 相關新聞
{news_lines}
"""


# 評級一致性校準（ADR-0010）：不重疊帶，評級由 value_score 決定
RATING_BANDS: dict[str, tuple[float, float]] = {
    "強力推薦": (85.0, 100.0),
    "值得關注": (70.0, 85.0),
    "中立觀望": (50.0, 70.0),
    "暫時避開": (0.0, 50.0),
}

RATING_ORDER = ["強力推薦", "值得關注", "中立觀望", "暫時避開"]


def _rating_from_score(value_score: float) -> str:
    """由 value_score 門檻決定評級（ADR-0010）。"""
    if value_score >= 85.0:
        return "強力推薦"
    if value_score >= 70.0:
        return "值得關注"
    if value_score >= 50.0:
        return "中立觀望"
    return "暫時避開"


def _enforce_rating_consistency(rating: str, value_score: float) -> str:
    """評級一致性：一律以 value_score 決定最終評級（分數驅動），
    避免 LLM 因評級帶重疊而集中單一評級（ADR-0010）。"""
    corrected = _rating_from_score(value_score)
    if rating and rating != corrected:
        logger.warning(
            "評級由分數驅動覆寫：LLM %s → %s（value_score=%.1f）",
            rating, corrected, value_score,
        )
    return corrected


def parse_deep_analysis(
    data: Any, fund_code: str, analysis_date: str
) -> DeepAnalysis:
    """將 LLM 回傳之 JSON 轉為 DeepAnalysis（缺欄以安全預設值補）。

    評級與 value_score 經一致性校準（ADR-0010）：帶外評級覆寫為門檻評級。
    """
    if not isinstance(data, dict):
        logger.warning("深度分析回應非物件（%s）：%r", fund_code, type(data).__name__)
        return DeepAnalysis(
            fund_code=fund_code,
            analysis_date=analysis_date,
            score_rationale="（LLM 回應格式異常，無法解析）",
        )
    sentiment = str(data.get("market_sentiment") or "Neutral").capitalize()
    if sentiment not in ("Positive", "Neutral", "Negative"):
        sentiment = "Neutral"
    try:
        value_score = float(data.get("value_score") or 0)
    except (TypeError, ValueError):
        value_score = 0.0
    value_score = max(0.0, min(100.0, value_score))

    llm_rating = str(data.get("overall_rating") or "")
    rating = _enforce_rating_consistency(llm_rating, value_score)

    return DeepAnalysis(
        fund_code=fund_code,
        analysis_date=analysis_date,
        news_summary=[str(x) for x in data.get("news_summary") or []],
        market_sentiment=sentiment,
        value_score=value_score,
        score_rationale=str(data.get("score_rationale") or ""),
        recommended_strategy=str(data.get("recommended_strategy") or ""),
        strategy_explanation=str(data.get("strategy_explanation") or ""),
        pros=[str(x) for x in data.get("pros") or []],
        cons=[str(x) for x in data.get("cons") or []],
        overall_rating=rating,
        llm_rating=llm_rating,
    )
