"""規則初評分測試。"""
from __future__ import annotations

from alphafund.models import Fund, NewsItem
from alphafund.scoring import momentum, news_volume, parse_return, preliminary_score, strategy_from_signals


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
    # (1*.15 + 3*.25 + 5*.25 + 10*.35) = 5.65
    assert abs(mom - 5.65) < 1e-6


def test_momentum_partial_fields():
    f = Fund(
        fund_code="A",
        name="X",
        returns={"navValue5": "-", "navValue6": "3", "navValue7": "-", "navValue8": "10"},
    )
    mom, _ = momentum(f)
    assert mom is not None
    # (3*.25 + 10*.35) / (.25+.35) = 7.0833
    assert abs(mom - 7.0833) < 1e-3


def test_preliminary_score_momentum_baseline():
    f = Fund(fund_code="A", name="X", returns={k: "5" for k in ("navValue5", "navValue6", "navValue7", "navValue8")})
    score, breakdown = preliminary_score(f, [])
    # mom=5 → 30 + 5*1.2 = 36.0
    assert breakdown["momentum_score"] == 36.0
    assert score == 36.0


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
