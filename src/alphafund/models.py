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
