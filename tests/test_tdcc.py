"""TDCC 客戶端測試（以 MockTransport 模擬，不觸網）。"""
from __future__ import annotations

import json

import httpx
import pytest

from alphafund.tdcc import TdccClient


def _make_client(handler):
    transport = httpx.MockTransport(handler)
    return TdccClient(base_url="https://test.local", transport=transport)


def test_warmup_then_query_org_basic():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/":
            return httpx.Response(200, text="<html></html>")
        assert request.url.path == "/api/offshore/org-info/org-search/query-org-basic"
        body = json.loads(request.content)
        assert body == {"orgType": "K"}
        return httpx.Response(
            200,
            json={"total": 1, "list": [{"orgCode": "K9800", "orgName": "元大證券"}]},
        )

    client = _make_client(handler)
    rows = client.query_org_basic("K")
    assert rows == [{"orgCode": "K9800", "orgName": "元大證券"}]
    client.close()


def test_query_all_funds_paginates():
    pages = {
        1: {
            "total": 350,
            "hasNextPage": True,
            "list": [{"fundCode": f"F{i}"} for i in range(200)],
        },
        2: {
            "total": 350,
            "hasNextPage": False,
            "list": [{"fundCode": f"F{i}"} for i in range(200, 350)],
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text="<html></html>")
        assert request.url.path == "/api/offshore/fund-info/fund-search/query"
        body = json.loads(request.content)
        page = body["_pageNum"]
        assert body["_pageSize"] == 200
        return httpx.Response(200, json=pages[page])

    client = _make_client(handler)
    records = client.query_all_funds(currency="all")
    assert len(records) == 350
    assert records[0]["fundCode"] == "F0"
    assert records[-1]["fundCode"] == "F349"
    client.close()


def test_query_org_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text="<html></html>")
        assert request.url.path == "/api/offshore/org-info/org-search/query-org-detail"
        body = json.loads(request.content)
        assert body == {"orgCode": "N0810"}
        return httpx.Response(
            200,
            json={"total": 2, "list": [{"fundCode": "A"}, {"fundCode": "B"}]},
        )

    client = _make_client(handler)
    rows = client.query_org_detail("N0810")
    assert {r["fundCode"] for r in rows} == {"A", "B"}
    client.close()


def test_query_dividend_paginates():
    pages = {
        1: {
            "total": 12,
            "hasNextPage": True,
            "list": [{"fundCode": "0385", "asiBaseDate": f"2026/01/0{i}"} for i in range(1, 11)],
        },
        2: {
            "total": 12,
            "hasNextPage": False,
            "list": [{"fundCode": "0385", "asiBaseDate": "2026/02/01"},
                     {"fundCode": "0385", "asiBaseDate": "2026/02/02"}],
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text="<html></html>")
        assert request.url.path == "/api/offshore/fund-info/info-dividend/query"
        assert request.headers["Referer"].endswith("/offshore/fund-info/info-dividend")
        body = json.loads(request.content)
        assert body["queryType"] == "0"
        assert body["searchName"] == "0385"
        assert body["baseBeginDate"] == "2025/08"
        assert body["baseEndDate"] == "2026/08"
        assert body["asiFreqList"] == []
        return httpx.Response(200, json=pages[body["_pageNum"]])

    client = _make_client(handler)
    records = client.query_dividend("0385", "2025/08", "2026/08")
    assert len(records) == 12
    assert records[0]["asiBaseDate"] == "2026/01/01"
    assert records[-1]["asiBaseDate"] == "2026/02/02"
    client.close()


def test_query_dividend_filters_substring_matches():
    """searchName 為子字串比對：0385 會命中 LU2861038557，需過濾僅留完全相符者。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(
            200,
            json={
                "total": 3,
                "hasNextPage": False,
                "list": [
                    {"fundCode": "0385", "asiBaseDate": "2026/07/31", "asiAmt": "0.031"},
                    {"fundCode": "LU2861038557", "asiBaseDate": "2026/07/31", "asiAmt": "1.200"},
                    {"fundCode": "0385", "asiBaseDate": "2026/06/30", "asiAmt": "0.030"},
                ],
            },
        )

    client = _make_client(handler)
    records = client.query_dividend("0385", "2025/08", "2026/08")
    assert [r["fundCode"] for r in records] == ["0385", "0385"]
    client.close()


def test_query_fund_details():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text="<html></html>")
        assert request.url.path == "/api/offshore/fund-basic/query-details"
        body = json.loads(request.content)
        assert body == {"fundCode": "1128"}
        return httpx.Response(
            200,
            json={
                "basicProfile": {"fundCode": "1128", "fundName": "黃金基金"},
                "fundType": {
                    "fundRiskLevelTxt": "RR5",
                    "fundAssetName": "股票型/黃金貴金屬",
                    "fundInvTypeName": "單一國家/瑞士",
                },
            },
        )

    client = _make_client(handler)
    d = client.query_fund_details("1128")
    assert d == {
        "risk_level": "RR5",
        "asset_class": "股票型/黃金貴金屬",
        "invest_type": "單一國家/瑞士",
    }
    client.close()


def test_query_fund_details_404_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(404, json={"message": "無資料"})

    client = _make_client(handler)
    assert client.query_fund_details("MISSING") == {}
    client.close()
