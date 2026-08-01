"""報告生成器測試。"""
from __future__ import annotations

from alphafund.report import render_calendar, render_report


def _sample_data():
    return {
        "date": "2026-08-01",
        "top_n": 1,
        "deep_analyzed_count": 1,
        "funds": [
            {
                "fund_code": "0352",
                "name": "富蘭克林坦伯頓全球投資系列-日本基金美元A (acc)股",
                "currency": "USD",
                "channels": ["元大證券", "匯豐銀行", "渣打銀行"],
                "preliminary_score": 93.9,
                "preliminary_breakdown": {"momentum_score": 84.9, "news_score": 9.0},
                "rank": 1,
                "status": "deep_analyzed",
                "deep_analysis": {
                    "news_summary": ["新聞重點一"],
                    "market_sentiment": "Positive",
                    "value_score": 85.0,
                    "score_rationale": "理由說明",
                    "recommended_strategy": "定期定額",
                    "strategy_explanation": "原因說明",
                    "pros": ["優勢一"],
                    "cons": ["風險一"],
                    "overall_rating": "值得關注",
                },
            },
            {
                "fund_code": "X9",
                "name": "某基金 <script>alert(1)</script>",
                "preliminary_score": 30.0,
                "preliminary_breakdown": {},
                "rank": 2,
                "status": "scored",
            },
        ],
    }


def _sample_nav():
    return {
        "0352": {
            "fund_code": "0352",
            "nav": "15.640000",
            "nav_date": "2026/07/30",
            "returns": {"navValue5": "1.0", "navValue8": "10.0"},
            "channels": [],
        }
    }


def test_render_report_contains_key_sections():
    html = render_report(_sample_data(), _sample_nav(), "2026-08-01")
    assert "<!DOCTYPE html>" in html
    assert "每日境外基金投研報告" in html
    assert "2026-08-01" in html
    assert "個案深度解讀" in html
    assert "免責聲明" in html
    assert "750 萬免稅額" in html


def test_render_report_detail_card_and_ranking():
    html = render_report(_sample_data(), _sample_nav(), "2026-08-01")
    assert 'id="fund-0352"' in html
    assert "定期定額" in html
    assert "新聞重點一" in html
    assert "理由說明" in html
    assert "<td class=\"num\">93.9</td>" in html  # 排名表含初評分


def test_render_report_escapes_html():
    html = render_report(_sample_data(), _sample_nav(), "2026-08-01")
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_render_report_compact_limits_ranking():
    html = render_report(_sample_data(), _sample_nav(), "2026-08-01", compact=True)
    assert "前 50 名排名" in html
    # 精簡版仍含個案卡片
    assert 'id="fund-0352"' in html
    assert "免責聲明" in html


def test_render_calendar_marks_available_dates():
    html = render_calendar(["2026-08-01", "2026-08-02"], "2026-08-01", base="archive/")
    assert 'id="cal"' in html
    # 連結由 JS 於執行期依 base + 日期動態組成，靜態 HTML 內嵌日期清單與 base
    assert '"archive/"' in html          # base 前綴嵌入
    assert '"2026-08-01"' in html        # 日期清單 JSON
    assert '"2026-08-02"' in html
    assert '"2026-08-01"' in html        # current 嵌入
    assert '"2026-08-03"' not in html


def test_render_calendar_empty_dates():
    html = render_calendar([], "2026-08-01")
    assert 'id="cal"' in html
    assert "byDate" in html


def test_render_report_injects_calendar_and_top_links():
    html = render_report(
        _sample_data(),
        _sample_nav(),
        "2026-08-01",
        calendar_html='<div id="cal" class="cal"></div>',
        top_links='<a href="../index.html">回最新</a>',
    )
    assert 'id="cal"' in html
    assert "回最新" in html
