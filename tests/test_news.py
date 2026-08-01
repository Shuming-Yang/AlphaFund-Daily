"""新聞模組測試。"""
from __future__ import annotations

import alphafund.news as news_mod
from alphafund.models import Fund, NewsItem


def test_fund_keyword_strips_share_class():
    f = Fund(
        fund_code="0352",
        name="富蘭克林坦伯頓全球投資系列-日本基金美元A (acc)股",
    )
    # WP3：基金特定關鍵字（distinctive 標的）
    assert news_mod.fund_keyword(f) == "日本基金"


def test_series_keyword_returns_series():
    f = Fund(
        fund_code="0352",
        name="富蘭克林坦伯頓全球投資系列-日本基金美元A (acc)股",
    )
    assert news_mod.series_keyword(f) == "富蘭克林坦伯頓全球投資系列"


def test_fund_keyword_without_dash():
    f = Fund(fund_code="X", name="某長名稱基金但無破折號很長很長很長很長很長很長")
    assert news_mod.fund_keyword(f) == "某長名稱基金但無破折號很長很長很長很長很長很長"[:50]


def test_fund_keyword_class_only_tail_falls_back_to_series():
    f = Fund(fund_code="B", name="霸菱韓國基金-A類美元累積型")
    assert news_mod.fund_keyword(f) == "霸菱韓國基金"


def test_fund_stem_and_distinctive():
    cases = [
        ("瀚亞投資-日本動力股票基金A (美元避險)", "日本動力股票基金"),
        ("聯博-國際科技基金S級別美元", "國際科技基金"),
        ("百達-生物科技-R 美元", "生物科技"),
        ("安本基金 - 日本永續股票基金  I 累積 美元避險", "日本永續股票基金"),
        ("瑞銀 (盧森堡) 新興市場債券基金 (美元) I-A1-累積", "瑞銀新興市場債券基金"),
    ]
    for name, expect in cases:
        assert news_mod.fund_distinctive(name) == expect, name


def test_fund_matches_title_and_series():
    f = Fund(fund_code="A", name="聯博-國際科技基金S級別美元")
    # 基金特定匹配：distinctive 標的在標題
    assert news_mod.fund_matches_title(f, "聯博國際科技基金 表現亮眼")
    assert news_mod.fund_matches_title(f, "國際科技基金 申購熱")
    # 系列匹配：僅系列名出現
    assert news_mod.fund_matches_series(f, "聯博全球非投資等級債券基金 吸引目光")
    # 基金特定不匹配系列新聞（跨基金污染防堵）
    assert not news_mod.fund_matches_title(f, "聯博全球非投資等級債券基金 吸引目光")


def test_is_low_signal_filters():
    assert news_mod.is_low_signal(NewsItem(title="X基金 的總覽 | 鉅亨網", source="鉅亨網"))
    assert news_mod.is_low_signal(NewsItem(title="X基金 淨值與總覽", source="CMoney"))
    assert news_mod.is_low_signal(NewsItem(title="X 召開年度股東常會", source="ezfunds.com.tw"))
    assert news_mod.is_low_signal(NewsItem(title="X 新增上架", source="ezfunds.com.tw"))
    assert not news_mod.is_low_signal(NewsItem(title="日本股市走強 相關基金受惠", source="經濟日報"))


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


def test_fetch_universe_news_dual_query_dedupes(monkeypatch, google_news_rss_xml):
    """雙查詢：基金特定（各檔一次）＋系列（同系列僅一次）→ 3 次呼叫，去重。"""
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
    # 日本基金(特定) + 東歐基金(特定) + 系列(一次) = 3 次
    assert calls["n"] == 3
    assert len(items) == 2  # 兩則新聞（跨呼叫去重）
