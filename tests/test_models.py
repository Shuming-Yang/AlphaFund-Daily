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


def test_annualized_yield_handles_thousand_comma_nav():
    """NAV 含千分位逗號仍可解析。"""
    f = Fund(
        fund_code="A",
        name="某高淨值基金",
        nav="1,037.770000",
        dividends=[DividendRecord(fund_code="A", amount=10.0), DividendRecord(fund_code="A", amount=10.0)],
    )
    assert f.annualized_yield() == 1.93  # 20 / 1037.77 × 100


def test_income_quality_missing_ratio_half():
    """缺比例資料之紀錄視為 50% 收益。"""
    f = Fund(
        fund_code="A",
        name="某入息基金",
        nav="10",
        dividends=[
            DividendRecord(fund_code="A", amount=0.1),                      # 缺比例 → 0.5
            DividendRecord(fund_code="A", amount=0.1, income_ratio=100.0),  # 全收益
        ],
    )
    assert f.income_quality() == 0.75  # (0.1×0.5 + 0.1×1.0)/0.2
    assert f.effective_yield() == 1.5  # 名目 2% × 0.75


def test_income_quality_principal_discount():
    """配息全來自本金（income_ratio=0）→ 品質 0、有效配息 0。"""
    f = Fund(
        fund_code="G",
        name="某總報酬配息基金",
        nav="10",
        dividends=[
            DividendRecord(fund_code="G", amount=0.5, income_ratio=0.0),
            DividendRecord(fund_code="G", amount=0.5, income_ratio=0.0),
        ],
    )
    assert f.income_quality() == 0.0
    assert f.effective_yield() == 0.0
    assert f.annualized_yield() == 10.0  # 名目配息率不變
