"""資料模型（pydantic）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


def _parse_amount(value: object) -> float:
    """解析 TDCC 配息金額（"-9999" 表無資料 → 0.0）。"""
    if value is None:
        return 0.0
    try:
        v = float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0
    return v if v > 0 else 0.0


def _parse_ratio(value: object) -> float | None:
    """解析配息來源比例（N/A / 非數值 → None）。"""
    if value is None:
        return None
    s = str(value).strip()
    if s in {"", "-", "N/A", "NA", "-9999"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


class FundRecord(BaseModel):
    """TDCC 機構查詢 / 基金搜尋回傳之原始記錄。"""

    fund_code: str
    fund_name: str
    fund_en_name: str = ""
    fund_pre_name: str = ""
    fund_pre_en_name: str = ""


class DividendRecord(BaseModel):
    """TDCC 配息資訊（境外基金）單筆配息紀錄。"""

    fund_code: str
    base_date: str = ""          # 配息基準日（YYYY/MM/DD）
    ex_date: str = ""            # 除息日
    pay_date: str = ""           # 配息發放日
    amount: float = 0.0          # 每單位配息金額
    frequency: str = ""          # 配息頻率（每月/每季…）
    principal_ratio: float | None = None  # 配息來源：本金比例（%）
    income_ratio: float | None = None     # 配息來源：收益比例（%）

    @classmethod
    def from_tdcc(cls, rec: dict) -> "DividendRecord":
        """自 TDCC info-dividend/query 回傳列建構（含 -9999 / N/A 容錯）。"""
        return cls(
            fund_code=str(rec.get("fundCode") or ""),
            base_date=str(rec.get("asiBaseDate") or ""),
            ex_date=str(rec.get("asiEnterDate") or ""),
            pay_date=str(rec.get("asiDate") or ""),
            amount=_parse_amount(rec.get("asiAmt")),
            frequency=str(rec.get("asiFreq") or ""),
            principal_ratio=_parse_ratio(rec.get("asiRatio1")),
            income_ratio=_parse_ratio(rec.get("asiRatio2")),
        )


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
    dividends: list[DividendRecord] = Field(default_factory=list)  # 近 N 月配息紀錄

    def annualized_yield(self, months: int = 12) -> float | None:
        """近 N 個月配息率（%）：Σ每單位配息 / 最新淨值 × 100。

        無淨值、無配息、或淨值非正數時回傳 None。
        """
        if not self.dividends:
            return None
        try:
            nav = float(self.nav)
        except (TypeError, ValueError):
            return None
        if nav <= 0:
            return None
        total = sum(d.amount for d in self.dividends if d.amount > 0)
        if total <= 0:
            return None
        return round(total / nav * 100.0, 2)


class NewsItem(BaseModel):
    """新聞項目。"""

    title: str
    url: str = ""
    source: str = ""
    published_at: str = ""
    summary: str = ""
    keywords: list[str] = Field(default_factory=list)  # 抓取時所用查詢關鍵字


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
    income_suitability: str = ""  # 長期投資+被動收入適合度（適合/普通/不適合）


class FundAnalysis(BaseModel):
    """單一基金的每日分析（初評分 + 可選深度分析）。"""

    fund_code: str
    name: str
    currency: str = ""
    channels: list[str] = Field(default_factory=list)
    preliminary_score: float = 0.0
    preliminary_breakdown: dict[str, Any] = Field(default_factory=dict)
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

