"""資料模型（pydantic）。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FundRecord(BaseModel):
    """TDCC 機構查詢 / 基金搜尋回傳之原始記錄。"""

    fund_code: str
    fund_name: str
    fund_en_name: str = ""
    fund_pre_name: str = ""
    fund_pre_en_name: str = ""


class Fund(BaseModel):
    """目標基金清單中的單一基金（級別）。"""

    fund_code: str
    name: str
    en_name: str = ""
    currency: str = ""          # ISO 代碼（USD）
    currency_name: str = ""     # TDCC 中文幣別
    nav: str = ""               # 最新淨值（原始字串，可能為 N/A）
    nav_date: str = ""          # 最新淨值日期（YYYY/MM/DD）
    returns: dict[str, str] = Field(default_factory=dict)  # 各期間報酬率
    channels: list[str] = Field(default_factory=list)      # 銷售通路中文名


class NewsItem(BaseModel):
    """新聞項目。"""

    title: str
    url: str = ""
    source: str = ""
    published_at: str = ""
    summary: str = ""


class DailySnapshot(BaseModel):
    """每日資料快照（存於 data/history/<date>/）。"""

    date: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    universe_count: int = 0
    funds: list[Fund] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)


class DeepAnalysis(BaseModel):
    """LLM 深度分析結果（評分矩陣 40/40/20，ADR-0003）。"""

    fund_code: str
    analysis_date: str = ""
    news_summary: list[str] = Field(default_factory=list)
    market_sentiment: str = ""   # Positive / Neutral / Negative
    value_score: float = 0.0     # 0–100
    score_rationale: str = ""
    recommended_strategy: str = ""   # 定期定額 / 分批單筆 / 觀望
    strategy_explanation: str = ""
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    overall_rating: str = ""     # 最終評級（分數驅動，ADR-0010）
    llm_rating: str = ""         # LLM 原始評級（供參考）


class FundAnalysis(BaseModel):
    """單一基金的每日分析（初評分 + 可選深度分析）。"""

    fund_code: str
    name: str
    currency: str = ""
    channels: list[str] = Field(default_factory=list)
    preliminary_score: float = 0.0
    preliminary_breakdown: dict[str, float] = Field(default_factory=dict)
    rank: int = 0
    deep_analysis: DeepAnalysis | None = None
    status: str = "scored"  # scored / deep_analyzed / quota_skipped / error
    provider: str = ""      # 深度分析實際使用的 LLM 供應商


class DailyAnalysis(BaseModel):
    """每日分析結果（存於 data/history/<date>/analysis.json.gz）。"""

    date: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    top_n: int = 0
    deep_analyzed_count: int = 0
    funds: list[FundAnalysis] = Field(default_factory=list)

