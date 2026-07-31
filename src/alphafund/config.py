"""專案設定與常數。

資料來源決策依 ADR-0001（TDCC 為主）與 ADR-0004（幣別僅 USD）。
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
HISTORY_DIR = DATA_DIR / "history"
UNIVERSE_FILE = DATA_DIR / "universe.json"

TIMEZONE = "Asia/Taipei"
REPORT_TIME = "06:00"

TDCC_BASE_URL = "https://www.fundclear.com.tw"

# 三家銷售通路（元大證券 / 匯豐銀行 / 渣打銀行）
# org_type：K=證券商，N=銀行（由機構查詢 API 取得）
CHANNELS: dict[str, dict[str, str]] = {
    "元大證券": {"org_type": "K", "org_code": "K9800"},
    "匯豐銀行": {"org_type": "N", "org_code": "N0810"},
    "渣打銀行": {"org_type": "N", "org_code": "N0520"},
}

# 計價幣別：TDCC 境外基金資料無新臺幣級別（見 ADR-0004），僅保留 USD。
ALLOWED_CURRENCIES: set[str] = {"USD"}

# TDCC 幣別中文名 → ISO 代碼
CURRENCY_NAME_MAP: dict[str, str] = {
    "美元": "USD",
    "澳幣": "AUD",
    "歐元": "EUR",
    "南非幣": "ZAR",
    "日幣": "JPY",
    "英鎊": "GBP",
    "新加坡幣": "SGD",
    "紐西蘭幣": "NZD",
    "港幣": "HKD",
    "加幣": "CAD",
    "瑞士法郎": "CHF",
    "瑞典幣": "SEK",
    "人民幣": "CNY",
    "新臺幣": "TWD",
    "台幣": "TWD",
}

DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# TDCC API 需要帶 Referer，否則回傳 403（見 m1-design.md）
REFERER_ORG_SEARCH = f"{TDCC_BASE_URL}/offshore/org-info/org-search"
REFERER_SALES_FUND = f"{TDCC_BASE_URL}/offshore/org-info/sales-fund"
REFERER_FUND_SEARCH = f"{TDCC_BASE_URL}/offshore/fund-info/fund-search"

TDCC_ORG_BASIC = "/api/offshore/org-info/org-search/query-org-basic"
TDCC_ORG_DETAIL = "/api/offshore/org-info/org-search/query-org-detail"
TDCC_FUND_QUERY = "/api/offshore/fund-info/fund-search/query"

FUND_PAGE_SIZE = 200

# 台媒財經 RSS 來源（M1 新聞池；可用性於執行期驗證）
TW_RSS_FEEDS: list[str] = [
    "https://ctee.com.tw/feed",
    "https://money.udn.com/rss/news/latest",
    "https://www.cna.com.tw/rss/twfinance.aspx",
]

GOOGLE_NEWS_BASE = "https://news.google.com/rss/search"
GOOGLE_NEWS_LANG = "zh-TW"
GOOGLE_NEWS_REGION = "TW"
GOOGLE_NEWS_CEID = "TW:zh-Hant"
