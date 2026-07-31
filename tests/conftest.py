"""共用測試 fixtures。"""
from __future__ import annotations

import pytest


@pytest.fixture
def sample_fund_records():
    """TDCC fund-search/query 記錄樣本（含各種幣別）。"""
    return [
        {
            "fundCode": "0352",
            "fundName": "富蘭克林坦伯頓全球投資系列-日本基金美元A (acc)股",
            "currencyName": "美元",
            "strNavLast": "15.640000",
            "strNavDate": "2026/07/30",
            "navValue5": "1.00",
            "navValue6": "2.00",
            "navValue7": "3.00",
            "navValue8": "4.00",
            "navValue9": "5.00",
            "navValue10": "-",
        },
        {
            "fundCode": "X1",
            "fundName": "某歐元基金",
            "currencyName": "歐元",
            "strNavLast": "1.200000",
            "strNavDate": "2026/07/30",
        },
        {
            "fundCode": "X2",
            "fundName": "某台幣基金",
            "currencyName": "新臺幣",
            "strNavLast": "10.000000",
            "strNavDate": "2026/07/30",
        },
        {
            "fundCode": "X3",
            "fundName": "某澳幣基金",
            "currencyName": "澳幣",
            "strNavLast": "1.000000",
            "strNavDate": "2026/07/30",
        },
        {
            "fundCode": "X4",
            "fundName": "未上架美元基金",
            "currencyName": "美元",
            "strNavLast": "5.000000",
            "strNavDate": "2026/07/30",
        },
    ]


@pytest.fixture
def channel_sets():
    """三家通路的上架基金代碼集合。"""
    return {
        "元大證券": {"0352", "X1", "X2", "X3"},
        "匯豐銀行": {"0352", "X1", "X3"},
        "渣打銀行": {"0352", "X1"},
    }


@pytest.fixture
def google_news_rss_xml():
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Google News</title>
    <item>
      <title>測試基金相關新聞</title>
      <link>https://example.com/news/1</link>
      <source url="https://news.example.com">鉅亨網</source>
      <pubDate>Fri, 31 Jul 2026 04:27:05 GMT</pubDate>
      <description>新聞摘要內容</description>
    </item>
    <item>
      <title>另一則測試新聞</title>
      <link>https://example.com/news/2</link>
      <source url="https://news2.example.com">經濟日報</source>
      <pubDate>Fri, 31 Jul 2026 05:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""
