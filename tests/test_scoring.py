"""規則初評分測試。"""
from __future__ import annotations

from alphafund.models import DividendRecord, Fund, NewsItem
from alphafund.scoring import (income_class_from_name, momentum, news_volume,
    parse_return, preliminary_score, stability_score, strategy_from_signals)


def test_parse_return():
    assert parse_return("12.71") == 12.71
    assert parse_return("12.71%") == 12.71
    assert parse_return("-") is None
    assert parse_return("N/A") is None
    assert parse_return("") is None


def test_momentum_weighted():
    f = Fund(
        fund_code="A",
        name="X",
        returns={"navValue5": "1", "navValue6": "3", "navValue7": "5", "navValue8": "10"},
    )
    mom, _ = momentum(f)
    assert mom is not None
    # 長期權重：(.05+.10+.20+.30)=.65 → (1*.05+3*.10+5*.20+10*.30)/.65 = 6.6923
    assert abs(mom - 6.6923) < 1e-3


def test_momentum_partial_fields():
    f = Fund(
        fund_code="A",
        name="X",
        returns={"navValue5": "-", "navValue6": "3", "navValue7": "-", "navValue8": "10"},
    )
    mom, _ = momentum(f)
    assert mom is not None
    # (.10+.30)=.40 → (3*.10+10*.30)/.40 = 8.25
    assert abs(mom - 8.25) < 1e-3


def test_preliminary_score_momentum_baseline():
    f = Fund(fund_code="A", name="X", returns={k: "5" for k in ("navValue5", "navValue6", "navValue7", "navValue8")})
    score, breakdown = preliminary_score(f, [])
    # mom=5 → 30 + 5*1.2 = 36；全部正報酬 → 穩定 +5 = 41（非配息型無收入加分）
    assert breakdown["momentum_score"] == 36.0
    assert breakdown["stability_bonus"] == 5.0
    assert score == 41.0


def test_preliminary_score_news_bonus():
    f = Fund(
        fund_code="A",
        name="測試全球基金-美元",
        returns={k: "0" for k in ("navValue5", "navValue6", "navValue7", "navValue8")},
    )
    news = [
        NewsItem(title="測試全球基金 表現強勁", url="u1"),
        NewsItem(title="測試全球基金 遭降評", url="u2"),
    ]
    score, breakdown = preliminary_score(f, news)
    assert breakdown["news_count"] == 2
    assert breakdown["news_score"] == 4.0  # min(10, 2*2)
    assert score == 34.0  # 30 + 4


def test_preliminary_score_news_capped_at_10():
    f = Fund(
        fund_code="A",
        name="測試全球基金-美元",
        returns={k: "0" for k in ("navValue5", "navValue6", "navValue7", "navValue8")},
    )
    news = [NewsItem(title=f"測試全球基金 新聞{i}", url=f"u{i}") for i in range(8)]
    score, breakdown = preliminary_score(f, news)
    assert breakdown["news_score"] == 10.0  # 5 則封頂 10 分
    assert score == 40.0


def test_news_volume_matches_only_related():
    f = Fund(fund_code="A", name="測試全球基金-美元", returns={})
    news = [
        NewsItem(title="測試全球基金 利多", url="u1"),
        NewsItem(title="完全不相干新聞", url="u2"),
    ]
    assert news_volume(f, news) == 1


def test_strategy_from_signals():
    # 1M 急漲 → 分批單筆
    f = Fund(fund_code="A", name="X", returns={"navValue5": "15", "navValue8": "20"})
    assert strategy_from_signals(f) == "分批單筆"
    # 1M 溫和、1Y 正 → 定期定額
    f = Fund(fund_code="B", name="Y", returns={"navValue5": "3", "navValue8": "20"})
    assert strategy_from_signals(f) == "定期定額"
    # 1Y 負 → 觀望
    f = Fund(fund_code="C", name="Z", returns={"navValue5": "3", "navValue8": "-5"})
    assert strategy_from_signals(f) == "觀望"
    # 無資料 → 定期定額
    f = Fund(fund_code="D", name="W", returns={})
    assert strategy_from_signals(f) == "定期定額"


def test_income_class_from_name():
    assert income_class_from_name("聯博全球非投資等級債券基金-TA類型(穩定月配)(美元)") == "配息型"
    # 揭露括號（配息來源可能為本金）不影響累積型判斷
    assert income_class_from_name("富蘭克林坦伯頓全球投資系列-科技基金美元A(acc)股(本基金之配息來源可能為本金)") == "累積型"
    assert income_class_from_name("某基金美元A累積") == "累積型"
    assert income_class_from_name("施羅德環球基金系列－環球企業債券(美元)A1-累積") == "累積型"
    assert income_class_from_name("完全無關鍵字基金") == "其他"
    assert income_class_from_name("") == "其他"


def test_stability_score():
    f = Fund(fund_code="A", name="X", returns={k: "5" for k in ("navValue5", "navValue6", "navValue7", "navValue8", "navValue9", "navValue10")})
    assert stability_score(f) == 1.0
    f2 = Fund(fund_code="B", name="Y", returns={"navValue5": "-5", "navValue6": "5", "navValue7": "-2", "navValue8": "8", "navValue9": "3", "navValue10": "1"})
    assert abs(stability_score(f2) - 4/6) < 1e-9  # 4/6 正


def test_preliminary_score_income_bonus():
    f = Fund(fund_code="A", name="聯博全球非投資等級債券基金-TA類型(穩定月配)(美元)", returns={k: "0" for k in ("navValue5", "navValue6", "navValue7", "navValue8")})
    score, breakdown = preliminary_score(f, [])
    # 配息型但無配息資料 → 保守底分 3（收入加分）；動能0→30、穩定0（全0非正）
    assert breakdown["income_bonus"] == 3.0
    assert breakdown["income_class"] == "配息型"
    assert breakdown["yield_pct"] == 0.0
    assert score == 33.0


def test_income_bonus_scales_with_yield():
    # 近12M 每單位配息 0.36、淨值 6.98 → 配息率 ≈ 5.16% → 5.16*1.5 ≈ 7.7 分
    f = Fund(
        fund_code="0385",
        name="富蘭克林坦伯頓全球投資系列-亞洲債券基金美元A(Mdis)股",
        nav="6.980000",
        dividends=[
            DividendRecord(fund_code="0385", base_date="2026/01/30", amount=0.031),
            DividendRecord(fund_code="0385", base_date="2026/02/27", amount=0.029),
            DividendRecord(fund_code="0385", base_date="2026/03/31", amount=0.032),
            DividendRecord(fund_code="0385", base_date="2026/04/30", amount=0.030),
            DividendRecord(fund_code="0385", base_date="2026/05/29", amount=0.031),
            DividendRecord(fund_code="0385", base_date="2026/06/30", amount=0.030),
            DividendRecord(fund_code="0385", base_date="2026/07/31", amount=0.031),
            DividendRecord(fund_code="0385", base_date="2025/08/29", amount=0.031),
            DividendRecord(fund_code="0385", base_date="2025/09/30", amount=0.029),
            DividendRecord(fund_code="0385", base_date="2025/10/31", amount=0.032),
            DividendRecord(fund_code="0385", base_date="2025/11/28", amount=0.030),
            DividendRecord(fund_code="0385", base_date="2025/12/31", amount=0.031),
        ],
    )
    yield_val = f.annualized_yield()
    assert yield_val is not None
    assert abs(yield_val - 5.26) < 0.02
    _, breakdown = preliminary_score(f, [])
    assert breakdown["income_class"] == "配息型"
    assert breakdown["income_bonus"] == 7.9  # 5.26 × 1.5 ≈ 7.89 → 7.9


def test_income_bonus_yield_capped():
    f = Fund(
        fund_code="B",
        name="某高配息基金美元(月配)",
        nav="10.000000",
        dividends=[
            DividendRecord(fund_code="B", base_date="2026/01/30", amount=1.0),
            DividendRecord(fund_code="B", base_date="2026/02/27", amount=1.0),
            DividendRecord(fund_code="B", base_date="2026/03/31", amount=1.0),
            DividendRecord(fund_code="B", base_date="2026/04/30", amount=1.0),
            DividendRecord(fund_code="B", base_date="2026/05/29", amount=1.0),
            DividendRecord(fund_code="B", base_date="2026/06/30", amount=1.0),
            DividendRecord(fund_code="B", base_date="2026/07/31", amount=1.0),
            DividendRecord(fund_code="B", base_date="2025/08/29", amount=1.0),
            DividendRecord(fund_code="B", base_date="2025/09/30", amount=1.0),
            DividendRecord(fund_code="B", base_date="2025/10/31", amount=1.0),
            DividendRecord(fund_code="B", base_date="2025/11/28", amount=1.0),
            DividendRecord(fund_code="B", base_date="2025/12/31", amount=1.0),
        ],
    )
    # 12M 配 12 → 配息率 120% → 加分封頂 10
    _, breakdown = preliminary_score(f, [])
    assert breakdown["income_bonus"] == 10.0


def test_non_dividend_fund_no_income_bonus():
    f = Fund(fund_code="C", name="某累積型基金-美元A(acc)股", nav="10.000000",
             returns={k: "5" for k in ("navValue5", "navValue6", "navValue7", "navValue8")})
    score, breakdown = preliminary_score(f, [])
    assert breakdown["income_class"] == "累積型"
    assert breakdown["income_bonus"] == 0.0
    assert breakdown["yield_pct"] == 0.0
