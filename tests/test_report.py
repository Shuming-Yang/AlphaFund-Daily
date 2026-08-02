"""報告生成器測試。"""
from __future__ import annotations

from alphafund.report import (
    INDEX_RANK_LIMIT,
    RANK_JUMP_THRESHOLD,
    _channel_stats,
    _navbar_html,
    _rank_delta_cell,
    _rank_toolbar_html,
    _trend_mini_table,
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
    assert f"前 {INDEX_RANK_LIMIT} 名排名" in html
    # 精簡版仍含個案卡片
    assert 'id="fund-0352"' in html
    assert "免責聲明" in html


def test_channel_stats_per_channel_totals():
    """每通路在清單內的總數（含跨通路上架）。"""
    stats = _channel_stats(_sample_data(), limit=2)
    assert stats["元大證券"] == 1   # 0352 於元大
    assert stats["匯豐銀行"] == 1   # 0352 於匯豐
    assert stats["渣打銀行"] == 1   # 0352 於渣打


def test_channel_stats_no_limit_uses_all():
    stats = _channel_stats(_sample_data(), limit=0)
    assert stats["元大證券"] == 1


def test_render_report_shows_three_channel_counts():
    html = render_report(
        _sample_data(), _sample_nav(), "2026-08-01", rank_limit=2
    )
    assert "通路（排名清單 2 內）" in html
    assert "元大" in html and "匯豐" in html and "渣打" in html
    assert "跨通路" not in html  # 不再顯示獨家/跨通路分類


def test_channel_badges_show_supported_channels():
    from alphafund.report import _channel_badges
    badges = _channel_badges(["元大證券", "渣打銀行"])
    # icon：SVG monogram + title 全名
    assert 'class="ch-icon"' in badges
    assert 'title="元大證券"' in badges
    assert 'title="渣打銀行"' in badges
    assert '<rect' in badges and "<text" in badges
    assert 'title="匯豐銀行"' not in badges
    assert _channel_badges([]) == ""


def test_channel_icon_colors():
    from alphafund.report import _channel_icon
    assert "#C8102E" in _channel_icon("元大證券")
    assert "#0072CE" in _channel_icon("匯豐銀行")
    assert "#00536D" in _channel_icon("渣打銀行")
    assert ">元<" in _channel_icon("元大證券")
    assert ">匯<" in _channel_icon("匯豐銀行")
    assert ">渣<" in _channel_icon("渣打銀行")


def test_ranking_rows_include_channel_badges():
    html = render_report(
        _sample_data(), _sample_nav(), "2026-08-01", rank_limit=2
    )
    assert "<th>通路</th>" in html
    assert 'class="ch-icon"' in html
    assert 'title="元大證券"' in html


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
    assert '<tr data-ch="元大證券,匯豐銀行,渣打銀行"' in html
    assert '<tr data-ch=""' in html


def test_ranking_rows_have_code_subtitle_and_data_search():
    html = render_report(_sample_data(), _sample_nav(), "2026-08-01")
    # 代號副標（名稱下方）
    assert '<span class="code">0352</span>' in html
    # data-search 供名稱/代號比對（lowercase）
    assert 'data-search="' in html
    assert "富蘭克林坦伯頓全球投資系列-日本基金美元a (acc)股 0352" in html


def test_ranking_rows_name_column_proportional_width():
    html = render_report(_sample_data(), _sample_nav(), "2026-08-01")
    # 排名表欄位寬度比例（#10 / 名稱58 / 初評分16 / 通路16）與靠左
    assert 'class="rank"' in html
    assert 'class="rank-name"' in html
    assert "table.rank th:nth-child(2),table.rank td:nth-child(2){width:58%}" in html
    assert "table.rank th:nth-child(1),table.rank td:nth-child(1){width:10%}" in html
    assert "width:16%;text-align:left" in html
    # 通路 icon 容器不換行
    assert "flex-wrap:nowrap" in html


def test_ranking_table_removed_low_value_columns():
    """排名表不再顯示情緒/購入模式（個案卡片保留）。"""
    html = render_report(_sample_data(), _sample_nav(), "2026-08-01")
    assert "<th>情緒</th>" not in html
    assert "<th>購入模式</th>" not in html
    # 個案卡片仍保留市場情緒與購入模式區塊
    assert "<h4>市場情緒</h4>" in html
    assert "<h4>購入模式</h4>" in html


def test_ranking_table_only_preliminary_score_and_channel():
    """排名表僅餘：#, 名稱, 初評分, 通路（深度分數/評級移至個案卡片）。"""
    html = render_report(_sample_data(), _sample_nav(), "2026-08-01")
    assert "<th>深度分數</th>" not in html
    assert "<th>評級</th>" not in html
    assert '<th class="num">初評分</th>' in html
    assert "<th>通路</th>" in html
    # 個案卡片 summary 仍顯示深度分數與評級
    assert "深度分數 85 · 初評分 93.9" in html
    assert 'class="rating r-值得關注"' in html


def test_detail_card_has_data_ch():
    html = render_report(_sample_data(), _sample_nav(), "2026-08-01")
    assert 'id="fund-0352" data-ch="元大證券,匯豐銀行,渣打銀行"' in html


def test_rank_toolbar_has_search_box():
    html = _rank_toolbar_html(_sample_data()["funds"], 0, show_channel=True)
    assert 'class="rank-search"' in html
    assert 'placeholder="🔍 搜尋名稱或代號"' in html
    assert "setSearch" in html
    assert "ch-chip" in html  # 通路篩選亦存在


def test_rank_toolbar_counts():
    funds = [
        {"channels": ["元大證券", "匯豐銀行"]},
        {"channels": ["元大證券"]},
        {"channels": ["渣打銀行"]},
    ]
    html = _rank_toolbar_html(funds, 0, show_channel=True)
    assert "全部 <b>3</b>" in html
    assert "元大證券 <b>2</b>" in html
    assert "匯豐銀行 <b>1</b>" in html
    assert "渣打銀行 <b>1</b>" in html
    assert "setChannel" in html  # vanilla JS 內嵌


def test_rank_toolbar_without_channel():
    html = _rank_toolbar_html(_sample_data()["funds"], 0, show_channel=False)
    assert 'class="rank-search"' in html
    # 未渲染通路 chip 按鈕（JS 中的 .ch-chip 字串屬正常程式碼）
    assert 'class="ch-chip' not in html


def test_rank_toolbar_limits_to_rows():
    funds = [
        {"channels": ["元大證券"]},
        {"channels": ["匯豐銀行"]},
        {"channels": ["渣打銀行"]},
    ]
    html = _rank_toolbar_html(funds, 2, show_channel=True)
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


def test_render_report_value_score_sparkline_when_sufficient():
    """深度分數（value_score）≥2 個非 None 點 → 個案卡片出現深度分數趨勢。"""
    series = {
        "0352": [
            TrendPoint(date="2026-07-31", preliminary_score=90.0, rank=1, value_score=85.0),
            TrendPoint(date="2026-08-01", preliminary_score=93.9, rank=1, value_score=88.0),
        ]
    }
    html = render_report(_sample_data(), _sample_nav(), "2026-08-01", series=series)
    assert "深度分數（僅深度分析日）" in html
    assert 'aria-label="深度分數 趨勢"' in html


def test_render_report_value_score_sparkline_hidden_when_sparse():
    """僅 1 個深度分數點 → 深度分數趨勢不顯示（避免單點圖）。"""
    series = {
        "0352": [
            TrendPoint(date="2026-07-31", preliminary_score=90.0, rank=1, value_score=85.0),
            TrendPoint(date="2026-08-01", preliminary_score=93.9, rank=1, value_score=None),
        ]
    }
    html = render_report(_sample_data(), _sample_nav(), "2026-08-01", series=series)
    assert "深度分數（僅深度分析日）" not in html
    assert 'aria-label="深度分數 趨勢"' not in html


def test_rank_delta_cell_jump_highlight():
    def series(deltas):
        pts = []
        for i, r in enumerate(deltas):
            pts.append(TrendPoint(date=f"2026-07-{31-i:02d}", preliminary_score=80.0, rank=r))
        return {"X": pts}

    # 大升 15 → jump-up
    up = _rank_delta_cell("X", series([20, 5]))
    assert 'class="jump-up"' in up and "▲15" in up
    # 大降 12 → jump-down
    down = _rank_delta_cell("X", series([5, 17]))
    assert 'class="jump-down"' in down and "▼12" in down
    # 小跳動 5 → 一般標示，無 jump class
    small = _rank_delta_cell("X", series([10, 5]))
    assert "jump" not in small and "▲5" in small
    assert RANK_JUMP_THRESHOLD == 10


def test_trend_mini_table_value_score_column():
    pts = [
        TrendPoint(date="2026-07-31", preliminary_score=90.0, rank=1, value_score=85.0),
        TrendPoint(date="2026-08-01", preliminary_score=93.9, rank=1, value_score=None),
    ]
    html = _trend_mini_table(pts)
    assert "深度分數" in html
    assert "<td class=\"num\">85</td>" in html   # 有深度分數日
    assert "<td class=\"num\">—</td>" in html    # 無深度分數日
