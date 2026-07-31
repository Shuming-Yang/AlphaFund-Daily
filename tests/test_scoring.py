"""規則初評分測試。"""
from __future__ import annotations

from alphafund.models import Fund, NewsItem
from alphafund.scoring import momentum, news_volume, parse_return, preliminary_score


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
    # mom=5 → 30 + 5*1.5 = 37.5
    assert breakdown["momentum_score"] == 37.5
    assert score == 37.5


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
    assert breakdown["news_score"] == 6.0  # min(15, 2*3)
    assert score == 36.0  # 30 + 6


def test_news_volume_matches_only_related():
    f = Fund(fund_code="A", name="測試全球基金-美元", returns={})
    news = [
        NewsItem(title="測試全球基金 利多", url="u1"),
        NewsItem(title="完全不相干新聞", url="u2"),
    ]
    assert news_volume(f, news) == 1
