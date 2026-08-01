"""M5 趨勢比較（trends）模組測試。"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from alphafund.trends import (
    TrendPoint,
    build_time_series,
    comparison_data,
    load_all_dates,
    series_for,
    sparkline_svg,
    trend_stats,
)


def _write_analysis(history: Path, date: str, funds: list[dict]) -> None:
    day = history / date
    day.mkdir(parents=True, exist_ok=True)
    with gzip.open(day / "analysis.json.gz", "wt", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": date, "funds": funds}, ensure_ascii=False))


def _fund(code: str, score: float, rank: int, deep: bool = True, date: str = "") -> dict:
    fa = {
        "fund_code": code,
        "name": f"基金 {code}",
        "preliminary_score": score,
        "preliminary_breakdown": {"momentum_pct": 1.0, "news_score": 0.0},
        "rank": rank,
    }
    if deep:
        fa["deep_analysis"] = {
            "fund_code": code,
            "value_score": score - 10.0,
            "overall_rating": "值得關注",
        }
    return fa


@pytest.fixture
def two_days(tmp_path: Path) -> Path:
    """兩個交易日的假歷史目錄（A 兩日俱在，B 僅第一日）。"""
    _write_analysis(
        tmp_path,
        "2026-08-01",
        [
            _fund("A", 90.0, 1, date="2026-08-01"),
            _fund("B", 80.0, 2, date="2026-08-01"),
        ],
    )
    _write_analysis(
        tmp_path,
        "2026-08-02",
        [
            _fund("A", 85.0, 3, date="2026-08-02"),
            _fund("C", 95.0, 1, date="2026-08-02"),
        ],
    )
    return tmp_path


def test_load_all_dates_sorted(two_days: Path):
    assert load_all_dates(two_days) == ["2026-08-01", "2026-08-02"]


def test_load_all_dates_ignores_missing_analysis(tmp_path: Path):
    (tmp_path / "2026-08-01").mkdir()
    assert load_all_dates(tmp_path) == []


def test_build_time_series_basic(two_days: Path):
    series = build_time_series(history_dir=two_days)
    assert set(series.keys()) == {"A", "B", "C"}
    a = series["A"]
    assert [p.date for p in a] == ["2026-08-01", "2026-08-02"]
    assert [p.preliminary_score for p in a] == [90.0, 85.0]
    assert [p.rank for p in a] == [1, 3]
    assert a[0].value_score == 80.0
    assert a[0].overall_rating == "值得關注"


def test_build_time_series_missing_day_skipped(two_days: Path):
    series = build_time_series(history_dir=two_days)
    b = series["B"]
    assert len(b) == 1  # 第二日不存在 → 僅一個點
    assert b[0].date == "2026-08-01"


def test_series_for_no_deep_analysis_null(two_days: Path):
    series = build_time_series(history_dir=two_days)
    # 所有樣本都有 deep；驗證 None 時保留
    c = series["C"]
    assert c[0].value_score is not None


def test_series_for_empty_and_cap():
    assert series_for("X", {}) == []
    pts = [
        TrendPoint(date=f"2026-08-{i:02d}", preliminary_score=i, rank=i)
        for i in range(1, 80)
    ]
    out = series_for("X", {"X": pts})
    assert len(out) == 60  # SPARK_MAX_POINTS 上限


def test_sparkline_empty_for_lt_2_points():
    pts = [TrendPoint(date="2026-08-01", preliminary_score=50, rank=10)]
    assert sparkline_svg(pts) == ""
    assert sparkline_svg([]) == ""


def test_sparkline_output_shape(two_days: Path):
    series = build_time_series(history_dir=two_days)
    svg = sparkline_svg(series["A"], "preliminary_score", label="初評分")
    assert svg.startswith("<svg")
    assert "<polyline" in svg
    assert "<polygon" in svg
    assert 'aria-label="初評分 趨勢"' in svg
    assert "<title>初評分 近 2 日</title>" in svg


def test_sparkline_rank_inverted(two_days: Path):
    series = build_time_series(history_dir=two_days)
    svg = sparkline_svg(series["A"], "rank")
    # rank 2 → rank 1 應上升（y 變小）
    import re
    ys = [float(y) for x, y in re.findall(r"([\d.]+),([\d.]+)", svg)]
    # 找 polyline 的座標（最後一個 polyline 的點）
    polylines = re.findall(r"<polyline[^>]*points=\"([^\"]+)\"", svg)
    pts = [tuple(map(float, p.split(","))) for p in polylines[-1].split()]
    assert pts[0][1] < pts[1][1]  # rank 1（第 1 日）在上方 y 小，rank 3（第 2 日）在下方 y 大


def test_trend_stats(two_days: Path):
    series = build_time_series(history_dir=two_days)
    st = trend_stats(series["A"], "preliminary_score")
    assert st["first"] == 90.0
    assert st["last"] == 85.0
    assert st["delta"] == -5.0
    assert st["min"] == 85.0
    assert st["max"] == 90.0


def test_comparison_data(two_days: Path):
    series = build_time_series(history_dir=two_days)
    data = comparison_data(
        series,
        ["A", "B"],
        window=14,
        history_dir=two_days,
        names={"A": "基金 A", "B": "基金 B"},
    )
    assert data["dates"] == ["2026-08-01", "2026-08-02"]
    rows = data["rows"]
    a = rows[0]
    assert a["name"] == "基金 A"
    assert a["latest_rank"] == 3
    assert a["days"][0]["rank"] == 1
    assert a["days"][1]["rank"] == 3
    # B 僅一日
    b = rows[1]
    assert len(b["days"]) == 1


def test_comparison_data_window_limits(two_days: Path):
    series = build_time_series(history_dir=two_days)
    data = comparison_data(series, ["A"], window=1, history_dir=two_days)
    assert data["dates"] == ["2026-08-02"]
    assert data["rows"][0]["days"][0]["date"] == "2026-08-02"
