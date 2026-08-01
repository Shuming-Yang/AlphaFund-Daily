"""M5 趨勢比較（Trend Comparison）— 歷史時序資料 + 行內 SVG 趨勢圖（ADR-0008）。

資料來源：`data/history/<date>/analysis.json.gz`（每日初評分／排名／深度評級）。
由 `data/history/` 累積日期建構各基金時間序列，並以純函式產生：
- 行內 SVG sparkline（無 JS 依賴、輸出確定、可單元測試）。
- 多日並排比較表資料結構。

趨勢至少需 2 個交易日才有意義；單日資料回傳空佔位並由 UI 顯示「累積中」。
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import HISTORY_DIR

DEFAULT_WINDOW = 14        # 多日比較表預設最近交易日數
SPARK_MAX_POINTS = 60      # sparkline 點數上限（控制體積）


@dataclass
class TrendPoint:
    """單一基金某交易日的時序點。deep 欄位於無深度分析時為 None。"""

    date: str
    preliminary_score: float
    rank: int
    value_score: float | None = None
    overall_rating: str | None = None
    momentum_pct: float | None = None


def load_all_dates(history_dir: Path | None = None) -> list[str]:
    """data/history/ 下有分析結果的日期（排序）。"""
    history_dir = history_dir or HISTORY_DIR
    dates = [
        d.name
        for d in history_dir.glob("????-??-??")
        if d.is_dir() and (d / "analysis.json.gz").exists()
    ]
    return sorted(dates)


def _load_analysis(history_dir: Path, date: str) -> dict:
    with gzip.open(history_dir / date / "analysis.json.gz", "rt", encoding="utf-8") as fh:
        return json.load(fh)


def build_time_series(
    dates: list[str] | None = None,
    history_dir: Path | None = None,
) -> dict[str, list[TrendPoint]]:
    """讀取全部日期 analysis，建立 fund_code → 依日期排序的 TrendPoint 序列。

    缺失日（某日基金不存在）不產生點位；deep 欄位於無深度分析時為 None。
    """
    history_dir = history_dir or HISTORY_DIR
    dates = dates if dates is not None else load_all_dates(history_dir)
    series: dict[str, list[TrendPoint]] = {}
    for date in dates:
        try:
            analysis = _load_analysis(history_dir, date)
        except OSError:
            continue
        for fa in analysis.get("funds", []):
            code = fa.get("fund_code")
            if not code:
                continue
            da = fa.get("deep_analysis") or {}
            point = TrendPoint(
                date=date,
                preliminary_score=float(fa.get("preliminary_score", 0.0)),
                rank=int(fa.get("rank", 0)),
                value_score=da.get("value_score"),
                overall_rating=da.get("overall_rating"),
                momentum_pct=(
                    fa.get("preliminary_breakdown") or {}
                ).get("momentum_pct"),
            )
            series.setdefault(code, []).append(point)
    return series


def series_for(code: str, series: dict[str, list[TrendPoint]]) -> list[TrendPoint]:
    """取得單一基金時序（最多 SPARK_MAX_POINTS 點，取最近）。"""
    pts = series.get(code, [])
    return pts[-SPARK_MAX_POINTS:]


def _values(points: list[TrendPoint], metric: str) -> list[float | None]:
    if metric == "rank":
        return [float(p.rank) for p in points]
    if metric == "value_score":
        return [p.value_score for p in points]
    return [p.preliminary_score for p in points]


def _svg_escape(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _polyline_attrs(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def sparkline_svg(
    points: list[TrendPoint],
    metric: str = "preliminary_score",
    width: int = 240,
    height: int = 56,
    label: str = "",
) -> str:
    """行內 SVG 趨勢線（ADR-0008）。<2 點回傳空字串（由 UI 顯示「累積中」）。

    - rank 反向：數值越小（排名越前）畫得越高。
    - 含面積填充、首尾/最小/最大值標籤與末值標註。
    """
    if not points:
        return ""
    vals = [(p, v) for p, v in zip(points, _values(points, metric)) if v is not None]
    if len(vals) < 2:
        return ""

    pad_l, pad_r, pad_t, pad_b = 6, 26, 8, 8
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    ys = [v for _, v in vals]
    lo, hi = min(ys), max(ys)
    if lo == hi:
        lo, hi = lo - 1, hi + 1
    if metric == "rank":
        def y_at(v: float) -> float:
            return pad_t + (v - lo) / (hi - lo) * plot_h  # 值小 → y 小（上方）
    else:
        def y_at(v: float) -> float:
            return pad_t + (hi - v) / (hi - lo) * plot_h

    n = len(vals)
    def x_at(i: int) -> float:
        return pad_l + (i / (n - 1)) * plot_w if n > 1 else pad_l

    coords = [(x_at(i), y_at(v)) for i, (_, v) in enumerate(vals)]
    pts = _polyline_attrs(coords)

    def fmt(v: float) -> str:
        if metric == "rank":
            return f"{v:.0f}" if v == int(v) else f"{v:.1f}"
        return f"{v:.0f}"

    first, last = vals[0][1], vals[-1][1]
    min_idx = min(range(n), key=lambda i: vals[i][1])
    max_idx = max(range(n), key=lambda i: vals[i][1])
    last_label = (
        f'<text x="{pad_l + plot_w + 3:.0f}" y="{y_at(last) + 3:.0f}" '
        f'font-size="9" fill="#1a1d21">{fmt(last)}</text>'
    )
    band = f'<text x="{pad_l}" y="{pad_t - 3:.0f}" font-size="8" fill="#6b7280">{fmt(max(vals[i][1] for i in range(n)))}</text>'

    title = f'<title>{_svg_escape(label)} 近 {n} 日</title>' if label else ""
    return (
        f'<svg class="spark" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{_svg_escape(label)} 趨勢">{title}'
        f'<polygon points="{pts} {x_at(n - 1):.1f},{pad_t + plot_h:.1f} {x_at(0):.1f},{pad_t + plot_h:.1f}" '
        f'fill="#0b5b8c" fill-opacity="0.08"/>'
        f'<polyline points="{pts}" fill="none" stroke="#0b5b8c" stroke-width="1.5" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'{band}{last_label}</svg>'
    )


def comparison_data(
    series: dict[str, list[TrendPoint]],
    top_codes: list[str],
    window: int = DEFAULT_WINDOW,
    history_dir: Path | None = None,
    names: dict[str, str] | None = None,
    dates: list[str] | None = None,
) -> dict[str, Any]:
    """多日並排比較資料：dates + 每檔基金的逐日 rank/score/rating。

    - dates：比較視窗內的交易日（最近 window 天）；未提供時自 history_dir 讀取。
    - rows：每檔基金，`days` 為該基金在視窗內逐日點位；`series` 為 (date, score, rank)。
    """
    if dates is None:
        dates = load_all_dates(history_dir)[-window:]
    else:
        dates = dates[-window:]
    names = names or {}
    rows = []
    for code in top_codes:
        pts = series.get(code, [])
        days = []
        for p in pts:
            if p.date in dates:
                days.append(
                    {
                        "date": p.date,
                        "rank": p.rank,
                        "score": round(p.preliminary_score, 1),
                        "rating": p.overall_rating,
                    }
                )
        rows.append(
            {
                "code": code,
                "name": names.get(code, ""),
                "latest_rank": pts[-1].rank if pts else None,
                "days": days,
                "series": [(p.date, round(p.preliminary_score, 1), p.rank) for p in pts[-window:]],
            }
        )
    return {"dates": dates, "rows": rows}


def trend_stats(points: list[TrendPoint], metric: str = "preliminary_score") -> dict:
    """區間統計：首/尾/高/低/平均與變化量。"""
    vals = [v for v in _values(points, metric) if v is not None]
    if not vals:
        return {}
    first, last = vals[0], vals[-1]
    stats = {
        "first": round(first, 1),
        "last": round(last, 1),
        "min": round(min(vals), 1),
        "max": round(max(vals), 1),
        "avg": round(sum(vals) / len(vals), 1),
        "delta": round(last - first, 1),
        "n": len(vals),
    }
    if metric == "rank":
        stats = {k: int(v) for k, v in stats.items() if k != "n"}
        stats["n"] = len(vals)
    return stats
