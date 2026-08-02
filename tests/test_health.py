"""健康監控模組測試。"""
from __future__ import annotations

import alphafund.health as health


def _sample_entries():
    return [
        {
            "date": "2026-08-01",
            "universe": 2128,
            "deep": 25,
            "quota_skipped": 2,
            "error": 0,
            "providers": {"openrouter": 20, "gemini": 5},
            "news": 400,
        },
        {
            "date": "2026-08-02",
            "universe": 2128,
            "deep": 25,
            "quota_skipped": 0,
            "error": 0,
            "providers": {"openrouter": 25},
            "news": 399,
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


def test_build_health_data_reads_history():
    entries = health.build_health_data()
    assert len(entries) >= 1
    for e in entries:
        assert {"date", "universe", "deep", "quota_skipped", "error", "providers", "news"} <= set(e)
        assert e["deep"] > 0  # 每日皆有深度分析
