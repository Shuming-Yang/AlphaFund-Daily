"""健康監控模組測試。"""
from __future__ import annotations

import alphafund.health as health


def _sample_entries():
    return [
        {
            "date": "2026-08-01",
            "universe": 2128,
            "deep": 25,
            "expected_deep": 25,
            "quota_skipped": 2,
            "error": 0,
            "providers": {"openrouter": 20, "gemini": 5},
            "news": 400,
            "run_status": "部分",
            "missing": [],
        },
        {
            "date": "2026-08-02",
            "universe": 2128,
            "deep": 25,
            "expected_deep": 25,
            "quota_skipped": 0,
            "error": 0,
            "providers": {"openrouter": 25},
            "news": 399,
            "run_status": "完整",
            "missing": [],
        },
    ]


def test_render_health_page_sections():
    html = health.render_health_page(_sample_entries(), '<nav class="navbar">nav</nav>')
    assert "系統健康" in html
    assert "每日執行狀態" in html
    assert "LLM 供應商使用彙總" in html
    assert "openrouter×20" in html  # 每日供應商分布
    assert "2026-08-01" in html
    assert "2" in html  # 歷史交易日
    assert "完整" in html and "部分" in html  # run 狀態
    assert "完成率" in html  # 摘要完成率


def test_build_health_data_reads_history():
    entries = health.build_health_data()
    assert len(entries) >= 1
    for e in entries:
        assert {"date", "universe", "deep", "expected_deep", "quota_skipped", "error", "providers", "news", "run_status", "missing"} <= set(e)
        assert e["deep"] > 0  # 每日皆有深度分析
        assert e["run_status"] in ("完整", "部分", "異常")


def test_health_navbar_no_calendar():
    """系統健康頁導覽不顯示「歷史日曆」選項（該頁無日曆面板）。"""
    from alphafund.report import _navbar_html
    from alphafund.pipeline import latest_date

    nav = _navbar_html(is_latest=True, date=latest_date(), active="health", show_calendar=False)
    assert "歷史日曆" not in nav
    assert "openCalPanel" not in nav
    assert 'class="active" href="health.html"' in nav
