"""快照寫入測試。"""
from __future__ import annotations

import gzip
import json

import httpx

import alphafund.pipeline as pipeline
from alphafund.models import DailySnapshot, Fund


def _snapshot() -> DailySnapshot:
    return DailySnapshot(
        date="2026-08-01",
        universe_count=1,
        funds=[
            Fund(
                fund_code="0352",
                name="測試基金",
                currency="USD",
                nav="1.500000",
                nav_date="2026/07/30",
            )
        ],
    )


def test_save_snapshot_writes_gzipped_history(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "HISTORY_DIR", tmp_path / "history")
    monkeypatch.setattr(pipeline, "UNIVERSE_FILE", tmp_path / "universe.json")

    day = pipeline.save_snapshot(_snapshot())

    assert (day / "snapshot.json.gz").exists()
    assert (day / "nav.json.gz").exists()
    assert (day / "news.json.gz").exists()
    assert (day / "universe.json.gz").exists()

    with gzip.open(day / "nav.json.gz", "rt", encoding="utf-8") as fh:
        nav = json.load(fh)
    assert nav[0]["fund_code"] == "0352"
    assert nav[0]["nav"] == "1.500000"

    # 最新清單為未壓縮，可直接讀取
    latest = json.loads((tmp_path / "universe.json").read_text(encoding="utf-8"))
    assert latest[0]["name"] == "測試基金"


def test_related_news_prefers_fund_specific():
    """WP3 分層：優先基金特定匹配；無則退系列層。"""
    from alphafund.models import Fund, NewsItem
    from alphafund.pipeline import related_news

    f = Fund(fund_code="A", name="聯博-國際科技基金S級別美元")
    news = [
        NewsItem(title="聯博國際科技基金 表現亮眼", url="u1"),
        NewsItem(title="聯博全球非投資等級債券基金 吸引目光", url="u2"),
    ]
    out = related_news(f, news)
    # 優先基金特定 → 只回傳第 1 筆
    assert [n.url for n in out] == ["u1"]


def test_related_news_series_fallback():
    """無基金特定新聞時退回系列層。"""
    from alphafund.models import Fund, NewsItem
    from alphafund.pipeline import related_news

    f = Fund(fund_code="A", name="聯博-國際科技基金S級別美元")
    news = [
        NewsItem(title="聯博全球非投資等級債券基金 吸引目光", url="u2"),
        NewsItem(title="完全不相干", url="u3"),
    ]
    out = related_news(f, news)
    assert [n.url for n in out] == ["u2"]


def test_dividend_window():
    from datetime import datetime

    begin, end = pipeline._dividend_window(12, ref=datetime(2026, 8, 2))
    assert (begin, end) == ("2025/08", "2026/08")
    begin, end = pipeline._dividend_window(12, ref=datetime(2026, 1, 15))
    assert (begin, end) == ("2025/01", "2026/01")


def test_fetch_dividends_only_for_candidates():
    """僅配息型／名稱含「收益」之基金會被查詢配息；累積型不查。"""
    from alphafund.models import DividendRecord
    from alphafund.tdcc import TdccClient

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text="<html></html>")
        assert request.url.path == "/api/offshore/fund-info/info-dividend/query"
        body = json.loads(request.content)
        fund_code = body["searchName"]
        if fund_code == "M1":  # 配息型 → 有配息
            return httpx.Response(
                200,
                json={"total": 1, "hasNextPage": False, "list": [
                    {"fundCode": "M1", "asiBaseDate": "2026/07/31", "asiAmt": "0.10"},
                ]},
            )
        if fund_code == "O2":  # 其他但名稱含收益 → 有配息
            return httpx.Response(
                200,
                json={"total": 1, "hasNextPage": False, "list": [
                    {"fundCode": "O2", "asiBaseDate": "2026/07/31", "asiAmt": "0.05"},
                ]},
            )
        # 累積型不應被查詢
        raise AssertionError(f"不應查詢 {fund_code}")

    transport = httpx.MockTransport(handler)
    client = TdccClient(base_url="https://test.local", transport=transport)
    funds = [
        Fund(fund_code="M1", name="某債券基金美元(月配)股"),
        Fund(fund_code="O2", name="M&G入息基金A(美元避險)(本基金並無保證收益及配息)"),
        Fund(fund_code="A3", name="某科技基金美元A(acc)股"),
    ]
    count = pipeline.fetch_dividends(client, funds)
    assert count == 2
    assert len(funds[0].dividends) == 1
    assert isinstance(funds[0].dividends[0], DividendRecord)
    assert funds[0].dividends[0].amount == 0.10
    assert len(funds[2].dividends) == 0  # 累積型未被查詢
    client.close()
