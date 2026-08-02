"""專案設定與常數。

資料來源決策依 ADR-0001（TDCC 為主）與 ADR-0004（幣別僅 USD）。
"""
from __future__ import annotations

import os
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
REFERER_DIVIDEND = f"{TDCC_BASE_URL}/offshore/fund-info/info-dividend"

TDCC_ORG_BASIC = "/api/offshore/org-info/org-search/query-org-basic"
TDCC_ORG_DETAIL = "/api/offshore/org-info/org-search/query-org-detail"
TDCC_FUND_QUERY = "/api/offshore/fund-info/fund-search/query"
TDCC_DIVIDEND_QUERY = "/api/offshore/fund-info/info-dividend/query"

# 配息查詢：以基金代碼當 searchName（關鍵字模式）精準查詢
TDCC_DIVIDEND_QUERY_TYPE = "0"  # 0=關鍵字查詢（境外）；1=境外機構查詢

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

# --- M2：LLM 供應商（ADR-0002 原則：零付費優先）---
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free"
)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

CLOUDFLARE_API_URL = "https://api.cloudflare.com/client/v4"
CLOUDFLARE_MODEL = os.environ.get(
    "CLOUDFLARE_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
)
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")

NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")

# LLM 供應商鏈：依序嘗試，某家 429/401/403 自動切換下一家（ADR-0007）
_chain_env = os.environ.get("LLM_PROVIDER_CHAIN", "").strip()
if _chain_env:
    LLM_PROVIDER_CHAIN = [p.strip() for p in _chain_env.split(",") if p.strip()]
elif os.environ.get("LLM_PROVIDER", "").strip():
    LLM_PROVIDER_CHAIN = [os.environ["LLM_PROVIDER"].strip()]
else:
    LLM_PROVIDER_CHAIN = ["openrouter", "gemini", "groq", "cloudflare", "nvidia"]

# 保留 LLM_PROVIDER 相容（= 鏈之首）
LLM_PROVIDER = LLM_PROVIDER_CHAIN[0]

TOP_N_DEEP_ANALYSIS = 15  # 免費額度 RPD≈17（gemini-3.6-flash）下的保守名額
GEMINI_TEMPERATURE = 0.2

# 報告排名表顯示上限（universe 仍為全體，僅顯示前 N 名）
RANKING_LIMIT = int(os.environ.get("RANKING_LIMIT", "500"))

# 投資模式（預設：長期投資 + 被動收入）
INVESTMENT_MODE = os.environ.get("INVESTMENT_MODE", "income_long_term")
INCOME_BONUS = float(os.environ.get("INCOME_BONUS", "10"))   # 配息收入加分上限
INCOME_YIELD_PER_POINT = float(os.environ.get("INCOME_YIELD_PER_POINT", "1.5"))  # 每 1% 配息率折算分數（6.7% → 滿分）
INCOME_BONUS_UNKNOWN = float(os.environ.get("INCOME_BONUS_UNKNOWN", "3"))  # 配息型但無配息資料之保守底分
STABILITY_MAX = float(os.environ.get("STABILITY_MAX", "5"))  # 穩定加分上限

# 配息率計算：近 N 個月配息總額 / 最新淨值
DIVIDEND_MONTHS = int(os.environ.get("DIVIDEND_MONTHS", "12"))
