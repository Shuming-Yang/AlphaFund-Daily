"""報告生成器測試。"""
from __future__ import annotations

from alphafund.report import (
    _channel_filter_html,
    _navbar_html,
    render_calendar,
    render_report,
)
from alphafund.trends import TrendPoint


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


def test_navbar_latest_vs_archive():
    latest = _navbar_html(is_latest=True, date="2026-08-01")
    assert 'class="active"' in latest
    assert "最新報告" in latest
    assert "歷史日曆" in latest

    archive = _navbar_html(is_latest=False, date="2026-08-01")
    assert "../index.html" in archive
    assert "2026-08-01" in archive  # 日期徽章
    assert 'class="active"' not in archive


def test_navbar_has_cal_panel_opener():
    html = _navbar_html(is_latest=True, date="2026-08-01")
    assert "openCalPanel" in html


def test_render_report_injects_calendar_and_nav():
    html = render_report(
        _sample_data(),
        _sample_nav(),
        "2026-08-01",
        calendar_html='<div id="cal" class="cal"></div>',
        nav_html='<nav class="navbar">導覽</nav>',
    )
    assert 'id="cal"' in html
    assert '<nav class="navbar">導覽</nav>' in html


def test_render_report_has_proportional_width():
    html = render_report(_sample_data(), _sample_nav(), "2026-08-01")
    assert "width:min(96%,1280px)" in html


def _sample_series() -> dict[str, list[TrendPoint]]:
    return {
        "0352": [
            TrendPoint(date="2026-07-31", preliminary_score=90.0, rank=1,
                       value_score=85.0, overall_rating="值得關注"),
            TrendPoint(date="2026-08-01", preliminary_score=93.9, rank=1,
                       value_score=85.0, overall_rating="值得關注"),
        ]
    }


def test_render_report_injects_trend_block():
    html = render_report(
        _sample_data(), _sample_nav(), "2026-08-01", series=_sample_series()
    )
    assert "📈 近期趨勢" in html
    assert '<svg class="spark"' in html
    assert "初評分 近 2 日" in html
    assert "排名（倒序" in html


def test_render_report_trend_insufficient_note():
    series = {
        "0352": [TrendPoint(date="2026-08-01", preliminary_score=90.0, rank=1)]
    }
    html = render_report(
        _sample_data(), _sample_nav(), "2026-08-01", series=series
    )
    assert "歷史資料累積中" in html
    assert '<svg class="spark"' not in html


def test_render_report_comparison_section():
    html = render_report(
        _sample_data(), _sample_nav(), "2026-08-01", series=_sample_series()
    )
    assert "📊 趨勢比較" in html
    assert "初評分並排表" in html
    assert "近窗變化" in html


def test_render_report_comparison_insufficient_note():
    series = {
        "0352": [TrendPoint(date="2026-08-01", preliminary_score=90.0, rank=1)]
    }
    html = render_report(
        _sample_data(), _sample_nav(), "2026-08-01", series=series
    )
    assert "歷史資料累積中：需 ≥2 個交易日" in html
    assert "近窗變化" not in html


def test_render_report_compact_skips_trends():
    html = render_report(
        _sample_data(), _sample_nav(), "2026-08-01",
        compact=True, series=_sample_series(),
    )
    assert "📈 近期趨勢" not in html
    assert "📊 趨勢比較" not in html
    assert '<svg class="spark"' not in html


def test_navbar_has_trends_link():
    latest = _navbar_html(is_latest=True, date="2026-08-01")
    assert 'href="trends.html"' in latest
    assert "📈 趨勢" in latest
    archive = _navbar_html(is_latest=False, date="2026-08-01")
    assert 'href="../trends.html"' in archive


def test_navbar_has_ranking_link():
    latest = _navbar_html(is_latest=True, date="2026-08-01")
    assert 'href="ranking.html"' in latest
    assert "🏆 完整排名" in latest
    archive = _navbar_html(is_latest=False, date="2026-08-01")
    assert 'href="../ranking.html"' in archive


def test_navbar_active_ranking():
    html = _navbar_html(is_latest=True, date="2026-08-01", active="ranking")
    assert 'class="active" href="ranking.html"' in html
    assert 'class="active" href="index.html"' not in html


def test_render_report_rank_limit_label():
    html = render_report(
        _sample_data(), _sample_nav(), "2026-08-01", rank_limit=100
    )
    assert "前 100 名排名" in html
    assert 'href="ranking.html"' in html


def test_ranking_rows_have_data_ch():
    html = render_report(_sample_data(), _sample_nav(), "2026-08-01")
    # 樣本基金通路 0352 三通路、X9 無通路
    assert '<tr data-ch="元大證券,匯豐銀行,渣打銀行">' in html
    assert '<tr data-ch="">' in html


def test_detail_card_has_data_ch():
    html = render_report(_sample_data(), _sample_nav(), "2026-08-01")
    assert 'id="fund-0352" data-ch="元大證券,匯豐銀行,渣打銀行"' in html


def test_channel_filter_html_counts():
    funds = [
        {"channels": ["元大證券", "匯豐銀行"]},
        {"channels": ["元大證券"]},
        {"channels": ["渣打銀行"]},
    ]
    html = _channel_filter_html(funds, 0)
    assert "ch-chip" in html
    assert "全部 <b>3</b>" in html
    assert "元大證券 <b>2</b>" in html
    assert "匯豐銀行 <b>1</b>" in html
    assert "渣打銀行 <b>1</b>" in html
    assert "setChannel" in html  # vanilla JS 內嵌


def test_channel_filter_html_limits_to_rows():
    funds = [
        {"channels": ["元大證券"]},
        {"channels": ["匯豐銀行"]},
        {"channels": ["渣打銀行"]},
    ]
    html = _channel_filter_html(funds, 2)
    assert "全部 <b>2</b>" in html
    assert "渣打銀行" not in html  # 第 3 檔不在前 2 列


def test_render_report_channel_filter_injected():
    html = render_report(
        _sample_data(), _sample_nav(), "2026-08-01",
        rank_limit=100, show_channel_filter=True,
    )
    assert 'class="ch-filters"' in html
    assert "銷售通路篩選" in html
    assert "setChannel" in html


def test_render_report_compact_no_channel_filter():
    html = render_report(
        _sample_data(), _sample_nav(), "2026-08-01",
        compact=True, show_channel_filter=True,
    )
    assert 'class="ch-filters"' not in html
