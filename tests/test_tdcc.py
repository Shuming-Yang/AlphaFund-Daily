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
