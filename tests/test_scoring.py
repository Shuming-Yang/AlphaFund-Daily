"""規則初評分測試（ADR-0012 穩定導向）。"""
from __future__ import annotations

from alphafund.models import DividendRecord, Fund, NewsItem
from alphafund.scoring import (growth_score, income_class_from_name,
    is_leveraged_name, long_term_return, momentum, news_volume,
    parse_return, preliminary_score, stability_persistence, stability_score,
    strategy_from_signals)


def _fund(code: str = "A", name: str = "X", returns: dict[str, str] | None = None,
          risk_level: str = "", nav: str = "",
          dividends: list[DividendRecord] | None = None) -> Fund:
    return Fund(
        fund_code=code,
        name=name,
        returns=returns or {},
        risk_level=risk_level,
        nav=nav,
        dividends=dividends or [],
    )


def test_parse_return():
    assert parse_return("12.71") == 12.71
    assert parse_return("12.71%") == 12.71
    assert parse_return("-") is None
    assert parse_return("N/A") is None
    assert parse_return("") is None


def test_momentum_weighted():
    f = _fund(returns={"navValue5": "1", "navValue6": "3", "navValue7": "5", "navValue8": "10"})
    mom, _ = momentum(f)
    assert mom is not None
    # 長期權重：(.05+.10+.20+.30)=.65 → (1*.05+3*.10+5*.20+10*.30)/.65 = 6.6923
    assert abs(mom - 6.6923) < 1e-3


def test_momentum_partial_fields():
    f = _fund(returns={"navValue5": "-", "navValue6": "3", "navValue7": "-", "navValue8": "10"})
    mom, _ = momentum(f)
    assert mom is not None
    # (.10+.30)=.40 → (3*.10+10*.30)/.40 = 8.25
    assert abs(mom - 8.25) < 1e-3


def test_growth_score_diminishing():
    """高獲利報酬遞減：100%→200% 僅差 ~2.6 分，不碾壓穩定型。"""
    assert abs(growth_score(_fund(returns={k: "5" for k in ("navValue6", "navValue7", "navValue8", "navValue9", "navValue10")}))[0] - 4.11) < 0.01
    assert abs(growth_score(_fund(returns={"navValue8": "100", "navValue9": "100", "navValue10": "100", "navValue7": "100"}))[0] - 32.13) < 0.01
    assert abs(growth_score(_fund(returns={"navValue8": "200", "navValue9": "200", "navValue10": "200", "navValue7": "200"}))[0] - 34.76) < 0.01


def test_long_term_return_excludes_short():
    """成長只計長線：1M/3M 暴衝不計入成長（短期高獲利不獲成長分）。"""
    f = _fund(returns={"navValue5": "50", "navValue6": "40", "navValue7": "3", "navValue8": "6", "navValue9": "10", "navValue10": "14"})
    lt = long_term_return(f)
    assert lt is not None
    # 6M/1Y/2Y/3Y = 0.15*3+0.30*6+0.25*10+0.30*14 = 8.95
    assert abs(lt - 8.95) < 1e-9
    assert growth_score(f)[0] < 10  # 雖 1M +50% 但長期僅 ~9 分


def test_stability_persistence_full():
    f = _fund(returns={k: "5" for k in ("navValue5", "navValue6", "navValue7", "navValue8", "navValue9", "navValue10")})
    s, detail = stability_persistence(f)
    assert s == 35.0
    assert detail["pos_long"] == 15.0
    assert detail["drawdown"] == 12.0
    assert detail["recent"] == 8.0


def test_stability_persistence_drawdown():
    """深回撤重罰：3M -20% → 回撤分全失，僅留長期持續 15 + 1M 反彈微 2。"""
    f = _fund(returns={"navValue5": "5", "navValue6": "-20", "navValue7": "5", "navValue8": "8", "navValue9": "12", "navValue10": "15"})
    s, detail = stability_persistence(f)
    assert s == 17.0
    assert detail["drawdown"] == 0.0
    assert detail["recent"] == 2.0


def test_preliminary_score_stable_beats_volatile():
    """核心原則：相同長期成長下，穩定型 > 高波動型（穩定成長 > 高波動）。"""
    returns_common = {"navValue7": "4", "navValue8": "8", "navValue9": "15", "navValue10": "22"}
    stable = _fund(returns={**returns_common, "navValue5": "1", "navValue6": "2"})
    volatile = _fund(returns={**returns_common, "navValue5": "-15", "navValue6": "-10"})
    s_stable, b_stable = preliminary_score(stable, [])
    s_volatile, b_volatile = preliminary_score(volatile, [])
    # 成長相同（~9.93），穩定分差 32 vs 17 → 穩定型勝出
    assert abs(b_stable["growth_score"] - b_volatile["growth_score"]) < 0.01
    assert b_stable["stability_score"] == 32.0
    assert b_volatile["stability_score"] == 17.0
    assert s_stable > s_volatile


def test_high_risk_gold_fund_pushed_down():
    """高波動金基金（深跌 + RR5）即使長期高漲幅也低於穩定型。"""
    gold = _fund(
        returns={"navValue5": "-20", "navValue6": "-15", "navValue7": "20", "navValue8": "60", "navValue9": "120", "navValue10": "180"},
        risk_level="RR5",
    )
    stable = _fund(
        returns={"navValue5": "1", "navValue6": "2", "navValue7": "4", "navValue8": "8", "navValue9": "15", "navValue10": "22"},
    )
    s_gold, b_gold = preliminary_score(gold, [])
    s_stable, _ = preliminary_score(stable, [])
    assert b_gold["risk_bonus"] == -8.0
    assert b_gold["stability_score"] <= 15.0
    assert s_gold < s_stable


def test_risk_bonus_rr_levels():
    cases = {"RR2": 1.5, "RR4": -4.0, "RR5": -8.0, "": 0.0, "RR9": 0.0}
    for rr, expected in cases.items():
        f = _fund(returns={k: "5" for k in ("navValue5", "navValue6", "navValue7", "navValue8", "navValue9", "navValue10")}, risk_level=rr)
        _, b = preliminary_score(f, [])
        assert b["risk_bonus"] == expected, rr
        assert b["risk_level"] == rr


def test_leverage_penalty_only_real_leverage():
    """槓桿/放空/反向 → -15；貨幣避險（對沖/Hedged）不誤傷。"""
    assert is_leveraged_name("某原油槓桿2倍基金")
    assert is_leveraged_name("某反向指數基金")
    assert is_leveraged_name("Some Daily 2x Leveraged Fund")
    assert is_leveraged_name("某放空型基金")
    # 貨幣避險級別不算槓桿
    assert not is_leveraged_name("摩根歐洲動力(美元對沖) - A股")
    assert not is_leveraged_name("貝萊德歐洲基金 Hedged A2 美元")
    assert not is_leveraged_name("某基金美元A2X級別")  # A2X 級別不誤判
    f = _fund(returns={k: "5" for k in ("navValue5", "navValue6", "navValue7", "navValue8", "navValue9", "navValue10")}, name="某原油槓桿2倍基金")
    _, b = preliminary_score(f, [])
    assert b["leverage_penalty"] == -15.0


def test_preliminary_score_news_bonus():
    f = _fund(name="測試全球基金-美元", returns={k: "0" for k in ("navValue5", "navValue6", "navValue7", "navValue8")})
    news = [
        NewsItem(title="測試全球基金 表現強勁", url="u1"),
        NewsItem(title="測試全球基金 遭降評", url="u2"),
    ]
    score, breakdown = preliminary_score(f, news)
    assert breakdown["news_count"] == 2
    assert breakdown["news_score"] == 4.0  # min(10, 2*2)
    assert score == 4.0  # 成長/穩定皆無資料 → 0


def test_preliminary_score_news_capped_at_10():
    f = _fund(name="測試全球基金-美元", returns={k: "0" for k in ("navValue5", "navValue6", "navValue7", "navValue8")})
    news = [NewsItem(title=f"測試全球基金 新聞{i}", url=f"u{i}") for i in range(8)]
    score, breakdown = preliminary_score(f, news)
    assert breakdown["news_score"] == 10.0  # 5 則封頂 10 分
    assert score == 10.0


def test_news_volume_matches_only_related():
    f = _fund(name="測試全球基金-美元", returns={})
    news = [
        NewsItem(title="測試全球基金 利多", url="u1"),
        NewsItem(title="完全不相干新聞", url="u2"),
    ]
    assert news_volume(f, news) == 1


def test_strategy_from_signals():
    # 1M 急漲 → 分批單筆
    f = _fund(returns={"navValue5": "15", "navValue8": "20"})
    assert strategy_from_signals(f) == "分批單筆"
    # 1M 溫和、1Y 正 → 定期定額
    f = _fund(code="B", returns={"navValue5": "3", "navValue8": "20"})
    assert strategy_from_signals(f) == "定期定額"
    # 1Y 負 → 觀望
    f = _fund(code="C", returns={"navValue5": "3", "navValue8": "-5"})
    assert strategy_from_signals(f) == "觀望"
    # 無資料 → 定期定額
    f = _fund(code="D", returns={})
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
    f = _fund(returns={k: "5" for k in ("navValue5", "navValue6", "navValue7", "navValue8", "navValue9", "navValue10")})
    assert stability_score(f) == 1.0
    f2 = _fund(code="B", returns={"navValue5": "-5", "navValue6": "5", "navValue7": "-2", "navValue8": "8", "navValue9": "3", "navValue10": "1"})
    assert abs(stability_score(f2) - 4 / 6) < 1e-9  # 4/6 正


def test_preliminary_score_income_bonus():
    f = _fund(name="聯博全球非投資等級債券基金-TA類型(穩定月配)(美元)", returns={k: "0" for k in ("navValue5", "navValue6", "navValue7", "navValue8")})
    score, breakdown = preliminary_score(f, [])
    # 配息型但無配息資料 → 保守底分 3（收入加分）；成長/穩定無資料 → 0
    assert breakdown["income_bonus"] == 3.0
    assert breakdown["income_class"] == "配息型"
    assert breakdown["yield_pct"] == 0.0
    assert score == 3.0


def test_income_bonus_scales_with_yield():
    f = _fund(
        code="0385",
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
    f = _fund(
        code="B",
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
    f = _fund(name="某累積型基金-美元A(acc)股", nav="10.000000",
              returns={k: "5" for k in ("navValue5", "navValue6", "navValue7", "navValue8")})
    _, breakdown = preliminary_score(f, [])
    assert breakdown["income_class"] == "累積型"
    assert breakdown["income_bonus"] == 0.0
    assert breakdown["yield_pct"] == 0.0
