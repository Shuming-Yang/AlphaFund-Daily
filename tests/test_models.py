"""資料模型測試：配息紀錄解析與配息率計算。"""
from __future__ import annotations

from alphafund.models import DividendRecord, Fund


def test_dividend_record_from_tdcc():
    rec = {
        "fundCode": "0385",
        "fundName": "某配息基金",
        "currencyName": "美元",
        "asiBaseDate": "2026/07/31",
        "asiEnterDate": "2026/08/01",
        "asiDate": "2026/08/08",
        "asiAmt": "0.031000000",
        "asiFreq": "每月",
        "asiRatio1": "68.00",
        "asiRatio2": "32.00",
    }
    d = DividendRecord.from_tdcc(rec)
    assert d.fund_code == "0385"
    assert d.base_date == "2026/07/31"
    assert d.amount == 0.031
    assert d.frequency == "每月"
    assert d.principal_ratio == 68.0
    assert d.income_ratio == 32.0


def test_dividend_record_handles_na():
    d = DividendRecord.from_tdcc(
        {"fundCode": "X", "asiAmt": "-9999", "asiRatio1": "N/A", "asiRatio2": ""}
    )
    assert d.amount == 0.0
    assert d.principal_ratio is None
    assert d.income_ratio is None


def test_annualized_yield():
    f = Fund(
        fund_code="A",
        name="某配息基金(月配)",
        nav="10.000000",
        dividends=[
            DividendRecord(fund_code="A", base_date="2026/01/31", amount=0.1),
            DividendRecord(fund_code="A", base_date="2026/02/28", amount=0.1),
            DividendRecord(fund_code="A", base_date="2026/03/31", amount=0.1),
        ],
    )
    # Σ0.3 / 10 × 100 = 3.0%
    assert f.annualized_yield() == 3.0


def test_annualized_yield_no_data_or_invalid_nav():
    f = Fund(fund_code="A", name="X", nav="10.000000")
    assert f.annualized_yield() is None
    f2 = Fund(fund_code="B", name="X", nav="N/A", dividends=[DividendRecord(fund_code="B", amount=0.1)])
    assert f2.annualized_yield() is None
    f3 = Fund(fund_code="C", name="X", nav="0", dividends=[DividendRecord(fund_code="C", amount=0.1)])
    assert f3.annualized_yield() is None
