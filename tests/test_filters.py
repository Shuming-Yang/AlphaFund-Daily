"""硬性過濾邏輯測試。"""
from __future__ import annotations

from alphafund.filters import currency_to_iso, filter_funds


def test_currency_to_iso():
    assert currency_to_iso("美元") == "USD"
    assert currency_to_iso("新臺幣") == "TWD"
    assert currency_to_iso("台幣") == "TWD"
    assert currency_to_iso("歐元") == "EUR"
    assert currency_to_iso("") == ""
    assert currency_to_iso("USD") == "USD"


def test_filter_funds_keeps_only_allowed_currency(sample_fund_records, channel_sets):
    funds = filter_funds(sample_fund_records, channel_sets)
    # 僅 0352（美元）與 X4（美元但未上架）中，X4 不在任何通路 → 僅 0352
    assert len(funds) == 1
    f = funds[0]
    assert f.fund_code == "0352"
    assert f.currency == "USD"
    assert f.nav == "15.640000"
    assert f.nav_date == "2026/07/30"


def test_filter_funds_aggregates_channels(sample_fund_records, channel_sets):
    funds = filter_funds(sample_fund_records, channel_sets)
    assert funds[0].channels == ["元大證券", "匯豐銀行", "渣打銀行"]


def test_filter_funds_drops_funds_not_in_any_channel(sample_fund_records, channel_sets):
    # X4 是美元但在三通路集合中皆無 → 不應出現在結果
    codes = {f.fund_code for f in filter_funds(sample_fund_records, channel_sets)}
    assert "X4" not in codes


def test_filter_funds_excludes_twd_when_not_allowed(sample_fund_records, channel_sets):
    # 預設 ALLOWED_CURRENCIES 僅含 USD → 新臺幣 X2 被排除
    funds = filter_funds(sample_fund_records, channel_sets)
    assert all(f.currency == "USD" for f in funds)
