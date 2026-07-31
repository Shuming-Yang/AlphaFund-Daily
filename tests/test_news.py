"""新聞模組測試。"""
from __future__ import annotations

import alphafund.news as news_mod
from alphafund.models import Fund


def test_fund_keyword_strips_share_class():
    f = Fund(
        fund_code="0352",
        name="富蘭克林坦伯頓全球投資系列-日本基金美元A (acc)股",
    )
    assert news_mod.fund_keyword(f) == "富蘭克林坦伯頓全球投資系列"


def test_fund_keyword_without_dash():
    f = Fund(fund_code="X", name="某長名稱基金但無破折號很長很長很長很長很長很長")
    assert news_mod.fund_keyword(f) == "某長名稱基金但無破折號很長很長很長很長很長很長"[:50]


def test_fetch_google_news_parses_rss(monkeypatch, google_news_rss_xml):
    class FakeResponse:
        status_code = 200
        content = google_news_rss_xml.encode()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(news_mod.httpx, "get", lambda *a, **k: FakeResponse())

    items = news_mod.fetch_google_news("測試基金")
    assert len(items) == 2
    assert items[0].title == "測試基金相關新聞"
    assert items[0].source == "鉅亨網"
    assert items[1].source == "經濟日報"


def test_fetch_universe_news_dedupes(monkeypatch, google_news_rss_xml):
    """同關鍵字只查一次；相同標題+網址去重。"""
    class FakeResponse:
        status_code = 200
        content = google_news_rss_xml.encode()

        def raise_for_status(self):
            pass

    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return FakeResponse()

    monkeypatch.setattr(news_mod.httpx, "get", fake_get)
    monkeypatch.setattr(news_mod.time, "sleep", lambda *a: None)

    funds = [
        Fund(fund_code="A", name="富蘭克林坦伯頓全球投資系列-日本基金"),
        Fund(fund_code="B", name="富蘭克林坦伯頓全球投資系列-東歐基金"),
    ]
    items = news_mod.fetch_universe_news(funds, max_per_fund=5)
    # 兩檔同一系列 → 關鍵字相同 → 僅 1 次查詢
    assert calls["n"] == 1
    assert len(items) == 2  # 兩則新聞
