"""三重硬性過濾：通路、幣別、收入屬性。

- 通路：基金須由三家銷售通路（元大/匯豐/渣打）任一上架。
- 幣別：計價幣別須在允許清單（僅 USD，見 ADR-0004）。
- 收入屬性：以 TDCC「境外基金」區為資料源，天然排除境內基金
  （ISIN 非 TW 開頭），故不需另做 ISIN 檢查。
"""
from __future__ import annotations

from .config import ALLOWED_CURRENCIES, CURRENCY_NAME_MAP
from .models import Fund


def currency_to_iso(currency_name: str) -> str:
    """TDCC 中文幣別 → ISO 代碼；無法辨識時回傳大寫原名。"""
    if not currency_name:
        return ""
    return CURRENCY_NAME_MAP.get(currency_name, currency_name.strip().upper())


def filter_funds(
    raw_records: list[dict],
    channel_sets: dict[str, set[str]],
    allowed_currencies: set[str] = ALLOWED_CURRENCIES,
) -> list[Fund]:
    """將 TDCC 基金搜尋記錄過濾為目標基金清單。

    raw_records 欄位對應 /api/offshore/fund-info/fund-search/query 的 list 項目。
    """
    results: dict[str, Fund] = {}

    for r in raw_records:
        code = str(r.get("fundCode", "")).strip()
        if not code:
            continue
        currency_name = (r.get("currencyName") or "").strip()
        iso = currency_to_iso(currency_name)
        if iso not in allowed_currencies:
            continue

        # 通路交集：記錄此基金出現在哪些通路
        channels = [name for name, codes in channel_sets.items() if code in codes]
        if not channels:
            continue

        fund = results.get(code)
        if fund is None:
            fund = Fund(
                fund_code=code,
                name=r.get("fundName") or "",
                en_name=r.get("fundEName") or "",
                currency=iso,
                currency_name=currency_name,
                nav=r.get("strNavLast") or "",
                nav_date=r.get("strNavDate") or "",
                returns={
                    k: (r.get(k) or "") for k in ("navValue5", "navValue6", "navValue7", "navValue8", "navValue9", "navValue10")
                },
                channels=channels,
            )
            results[code] = fund
        else:
            for ch in channels:
                if ch not in fund.channels:
                    fund.channels.append(ch)

    return sorted(results.values(), key=lambda f: f.fund_code)
