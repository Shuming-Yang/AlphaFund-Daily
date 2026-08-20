"""每日報告 HTML5 單頁生成器（M3）。

讀取 `analysis.json.gz`（+ `nav.json.gz`）→ 產出 `docs/index.html`：
- 頂部：報告日期、統計摘要、排名表（完整清單於 `<details>` 內可收合）。
- 個案：前段基金（有深度分析者）各一個 `<details>` 折疊卡片，
  含新聞摘要、評分理由、購入模式、優劣勢與稅務標籤。
- 頁首印日期；頁尾免責聲明與資料來源。
"""
from __future__ import annotations

import gzip
import html as html_mod
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import CHANNELS, HISTORY_DIR, PROJECT_ROOT, TIMEZONE
from .models import Fund
from .news import fund_matches_series, fund_matches_title
from .scoring import income_class_from_name
from .trends import (
    DEFAULT_WINDOW,
    TrendPoint,
    build_time_series,
    comparison_data,
    load_all_dates,
    series_for,
    sparkline_svg,
    trend_stats,
)

REPORT_FILE = PROJECT_ROOT / "docs" / "index.html"
TRENDS_FILE = PROJECT_ROOT / "docs" / "trends.html"
RANKING_FILE = PROJECT_ROOT / "docs" / "ranking.html"

# 首頁排名表列數上限（完整排名移至 docs/ranking.html，控制 index 體積）
INDEX_RANK_LIMIT = 500

# 排名跳動高亮門檻：視窗首日→末日 |Δrank| 達此值即標記大幅變動
RANK_JUMP_THRESHOLD = 10

_PERIODS = [
    ("1月", "navValue5"),
    ("3月", "navValue6"),
    ("6月", "navValue7"),
    ("1年", "navValue8"),
    ("2年", "navValue9"),
    ("3年", "navValue10"),
]

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1a1d21;--mut:#6b7280;--line:#e5e7eb;
--brand:#0b5b8c;--pos:#0a7a3d;--neg:#b02a2a;--neu:#8a6d1d;}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Noto Sans TC","PingFang TC",sans-serif;
background:var(--bg);color:var(--ink);line-height:1.6}
.wrap{width:min(96%,1280px);margin:0 auto;padding:24px 16px 48px}
.navbar{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.96);backdrop-filter:blur(6px);
border-bottom:1px solid var(--line)}
.nav-inner{width:min(96%,1280px);margin:0 auto;display:flex;align-items:center;justify-content:space-between;
padding:10px 16px;flex-wrap:wrap;row-gap:6px}
.brand{font-weight:700;color:var(--brand);font-size:15px}
.nav-links{display:flex;align-items:center;gap:4px}
.nav-links a{color:var(--mut);text-decoration:none;font-size:13px;padding:5px 10px;border-radius:6px;white-space:nowrap}
.nav-links a:hover{background:#eef1f4;color:var(--ink)}
.nav-links a.active{background:var(--brand);color:#fff;font-weight:600}
.date-badge{font-size:12px;color:var(--mut);border:1px solid var(--line);border-radius:20px;
padding:2px 10px;margin-left:6px;background:#fafbfc}
.cal-wrap{border:none;background:none;padding:0;margin:0 0 4px}
.cal-wrap summary{cursor:pointer;color:var(--brand);font-size:13px;list-style:none;padding:4px 0;width:fit-content}
.cal-wrap summary::-webkit-details-marker{display:none}
header h1{font-size:22px;margin:0 0 4px;color:var(--brand)}
header .meta{color:var(--mut);font-size:13px}
.stat-row{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:10px 16px;min-width:120px}
.stat b{font-size:20px;display:block}
.stat span{font-size:12px;color:var(--mut)}
h2{font-size:16px;margin:28px 0 10px;border-left:4px solid var(--brand);padding-left:8px}
table{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--line);border-radius:8px;overflow:hidden}
th,td{text-align:left;padding:7px 10px;font-size:13px;border-bottom:1px solid var(--line)}
th{background:#eef1f4;position:sticky;top:0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.rating{display:inline-block;padding:1px 8px;border-radius:20px;font-size:12px;white-space:nowrap}
.r-強力推薦{background:#d3f0dd;color:var(--pos)}
.r-值得關注{background:#fff3d0;color:var(--neu)}
.r-中立觀望{background:#e5e7eb;color:var(--mut)}
.r-暫時避開{background:#f7d6d6;color:var(--neg)}
.sent-p{color:var(--pos)}.sent-n{color:var(--neg)}.sent-u{color:var(--mut)}
details{border:1px solid var(--line);border-radius:10px;background:var(--card);
margin:10px 0;padding:0 16px}
details[open]{box-shadow:0 2px 8px rgba(0,0,0,.06)}
summary{cursor:pointer;padding:12px 0;font-size:14px;list-style:none}
summary::-webkit-details-marker{display:none}
summary .g{color:var(--mut);margin-right:6px}
.f-body{padding:0 0 14px;font-size:13px}
.f-body .col{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin:8px 0}
.f-body .blk{background:#fafbfc;border:1px solid var(--line);border-radius:8px;padding:8px 12px}
.f-body .blk h4{margin:0 0 4px;font-size:12px;color:var(--mut)}
.tax{border:1px dashed var(--brand);background:#eef6fb;border-radius:8px;padding:8px 12px;font-size:12px;margin-top:10px}
ul{margin:4px 0;padding-left:18px}
footer{margin-top:36px;border-top:1px solid var(--line);padding-top:14px;
font-size:12px;color:var(--mut)}
.cal{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;margin:14px 0}
.cal-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.cal-head button{background:#eef1f4;border:1px solid var(--line);border-radius:6px;padding:4px 10px;cursor:pointer;font-size:13px}
.cal-title{font-weight:600;font-size:14px}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;text-align:center}
.cal-grid .dow{font-size:11px;color:var(--mut);padding:2px 0}
.cal-grid .day{font-size:12px;padding:4px 0;border-radius:6px;color:#b0b6bd}
.cal-grid .day a{display:block;color:var(--brand);text-decoration:none;font-weight:600;border-radius:6px}
.cal-grid .day a:hover{background:#e5f1f8}
.cal-grid .day.today a{outline:1px solid var(--brand)}
.spark{display:block;margin:2px 0;max-width:100%}
.trend-blk h4{margin:6px 0 2px;font-size:12px;color:var(--mut)}
.trend-metric{font-size:11px;color:var(--mut);display:block;margin-top:4px}
.trend-note{font-size:12px;color:var(--mut)}
.trend-stats{font-size:11px;color:var(--mut);margin-top:4px}
table.mini{margin-top:6px;border:1px solid var(--line);border-radius:6px}
table.mini th,table.mini td{padding:2px 8px;font-size:11px;text-align:right}
table.mini th:first-child,table.mini td:first-child{text-align:left}
.cmp-scroll{overflow-x:auto;border-radius:8px}
table.cmp th,table.cmp td{white-space:nowrap}
td.cmp-rank,th.cmp-rank{text-align:center}
td.cmp-miss{color:#b0b6bd;text-align:center}
.cmp-foot{font-size:11px;color:var(--mut);margin-top:4px}
.trend-hero{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:10px 0}
.trend-hero h3{margin:0 0 2px;font-size:15px}
.trend-hero .sub{font-size:12px;color:var(--mut)}
.trend-charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px;margin:10px 0}
.trend-chart{border:1px solid var(--line);border-radius:8px;padding:8px 10px;background:#fafbfc}
.trend-chart h4{margin:0 0 6px;font-size:12px;color:var(--mut)}
.trend-chart svg{width:100%;height:auto}
.ch-filters{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:10px 0}
.ch-label{font-size:13px;color:var(--mut)}
.ch-chip{border:1px solid var(--line);background:var(--card);border-radius:20px;padding:3px 12px;font-size:13px;cursor:pointer;color:var(--ink)}
.ch-chip b{font-weight:600;opacity:.75;margin-left:2px}
.ch-chip:hover{background:#eef1f4}
.ch-chip.active{background:var(--brand);color:#fff;border-color:var(--brand);font-weight:600}
.ch-chip.active b{opacity:.9;color:#fff}
.ch-dist{font-size:13px;color:var(--ink);margin:12px 0 0}
.ch-dist b{font-variant-numeric:tabular-nums}
.ch-badges{display:inline-flex;justify-content:flex-end;gap:3px;flex-wrap:nowrap;white-space:nowrap;align-items:center}
.ch-icon{display:inline-flex;line-height:0;vertical-align:middle}
.ch-icon svg{display:block}
table.rank th:nth-child(1),table.rank td:nth-child(1){width:8%}
table.rank th:nth-child(2),table.rank td:nth-child(2){width:60%}
table.rank th:nth-child(3),table.rank td:nth-child(3),
table.rank th:nth-child(4),table.rank td:nth-child(4){width:16%;text-align:left}
table.rank .ch-badges{justify-content:flex-start}
.rank-name a{overflow-wrap:break-word;word-break:break-word}
.code{display:block;font-size:11px;color:var(--mut);font-weight:400}
.code-sum{font-size:11px;color:var(--mut);margin-left:6px}
.yield-tag{display:inline-block;margin-left:8px;padding:0 6px;border-radius:4px;font-size:11px;
color:var(--acc,#2f7a57);background:rgba(47,122,87,.12);white-space:nowrap}
.rr-tag{display:inline-block;margin-left:8px;padding:0 6px;border-radius:4px;font-size:11px;
color:var(--mut,#8a6d3b);background:rgba(180,140,60,.14);white-space:nowrap}
.rank-toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:10px 0}
.rank-search{padding:6px 12px;border:1px solid var(--line);border-radius:8px;font-size:13px;
background:var(--card);color:var(--ink);min-width:220px;flex:1 1 240px}
.rank-search:focus{outline:2px solid var(--brand);outline-offset:-1px}
.jump-up{background:#d3f0dd;color:var(--pos);font-weight:700;border-radius:6px;padding:1px 6px;white-space:nowrap}
.jump-down{background:#f7d6d6;color:var(--neg);font-weight:700;border-radius:6px;padding:1px 6px;white-space:nowrap}
@media (max-width:640px){.f-body .col{grid-template-columns:1fr}}
"""


def _available_dates() -> list[str]:
    """data/history/ 下所有有分析結果的日期（排序）。"""
    dates = [
        d.name
        for d in HISTORY_DIR.glob("????-??-??")
        if d.is_dir() and (d / "analysis.json.gz").exists()
    ]
    return sorted(dates)


def _calendar_js(dates: list[str], current: str, base: str) -> str:
    dates_json = json.dumps(sorted(dates))
    base_js = json.dumps(base)
    return f"""<script>
(function(){{
  var dates = {dates_json};
  var byDate = {{}};
  dates.forEach(function(d){{ byDate[d] = true; }});
  var current = {json.dumps(current)};
  var base = {base_js};
  var y = parseInt(current.slice(0,4),10), m = parseInt(current.slice(5,7),10);
  var MONTHS = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
  function pad(n){{ return n<10 ? '0'+n : ''+n; }}
  function render(){{
    var first = new Date(y, m-1, 1);
    var startDow = first.getDay();
    var daysInMonth = new Date(y, m, 0).getDate();
    var html = '<div class="cal-head"><button onclick="calNav(-1)">‹ 上月</button>' +
      '<span class="cal-title">' + y + ' 年 ' + MONTHS[m-1] + '</span>' +
      '<button onclick="calNav(1)">下月 ›</button></div><div class="cal-grid">';
    ['日','一','二','三','四','五','六'].forEach(function(d){{ html += '<span class="dow">' + d + '</span>'; }});
    for (var i=0;i<startDow;i++){{ html += '<span class="day"></span>'; }}
    for (var d=1; d<=daysInMonth; d++){{
      var key = y + '-' + pad(m) + '-' + pad(d);
      var cls = 'day';
      if (key === current) {{ cls += ' today'; }}
      if (byDate[key]) {{ html += '<span class="'+cls+'"><a href="' + base + key + '.html">' + d + '</a></span>'; }}
      else {{ html += '<span class="'+cls+'">' + d + '</span>'; }}
    }}
    html += '</div>';
    document.getElementById('cal').innerHTML = html;
  }}
  window.calNav = function(delta){{
    m += delta;
    if (m < 1) {{ m = 12; y--; }}
    if (m > 12) {{ m = 1; y++; }}
    render();
  }};
  render();
  window.openCalPanel = function(){{
    var p = document.getElementById('cal-panel');
    if (p) {{ p.open = true; p.scrollIntoView({{ behavior: 'smooth' }}); }}
  }};
}})();
</script>"""


def render_calendar(dates: list[str], current: str, base: str = "archive/") -> str:
    """月曆 widget：可點選有報告的日期；base 為 archive 頁相對前綴。"""
    return (
        '<div id="cal" class="cal" aria-label="歷史報告日曆"></div>\n'
        + _calendar_js(dates, current, base)
    )


def _calendar_panel(dates: list[str], current: str, base: str) -> str:
    """月曆收合面板（預設關閉，點 navbar「歷史日曆」展開）。"""
    return (
        '<details id="cal-panel" class="cal-wrap">'
        "<summary>📅 歷史日曆（預設收合，點此或上方導覽展開）</summary>"
        + render_calendar(dates, current, base)
        + "</details>"
    )


def _navbar_html(
    is_latest: bool,
    date: str,
    active: str | None = None,
    show_calendar: bool = True,
) -> str:
    """固定頂部導覽列；active 指定目前頁面（index / ranking / trends / health），預設 index（archive 頁無高亮）。

    show_calendar 控制是否顯示「歷史日曆」連結：僅有 cal-panel 之頁面（最新報告/archive）才顯示；
    ｜完整排名｜趨勢｜系統健康｜等頁面無日曆面板，不顯示此連結。
    """
    active = active if active is not None else ("index" if is_latest else "")
    trends_href = "trends.html" if is_latest else "../trends.html"
    ranking_href = "ranking.html" if is_latest else "../ranking.html"
    index_href = "index.html" if is_latest else "../index.html"
    health_href = "health.html" if is_latest else "../health.html"
    calendar_link = (
        '<a href="#" onclick="openCalPanel();return false;">📅 歷史日曆</a>'
        if show_calendar
        else ""
    )

    def link(href: str, label: str, key: str) -> str:
        cls = ' class="active"' if active == key else ""
        return f'<a{cls} href="{href}">{label}</a>'

    if is_latest:
        links = (
            link(index_href, "最新報告", "index")
            + link(ranking_href, "🏆 完整排名", "ranking")
            + link(trends_href, "📈 趨勢", "trends")
            + link(health_href, "🩺 系統健康", "health")
            + calendar_link
        )
    else:
        links = (
            link(index_href, "← 最新報告", "index")
            + link(ranking_href, "🏆 完整排名", "ranking")
            + link(trends_href, "📈 趨勢", "trends")
            + link(health_href, "🩺 系統健康", "health")
            + calendar_link
            + f'<span class="date-badge">{_esc(date)}</span>'
        )
    return (
        '<nav class="navbar"><div class="nav-inner">'
        '<span class="brand">AlphaFund-Daily</span>'
        f'<span class="nav-links">{links}</span>'
        "</div></nav>"
    )


def _esc(value: object) -> str:
    return html_mod.escape(str(value if value is not None else ""), quote=True)


def _load_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def load_report_data(date: str) -> tuple[dict, dict[str, dict], list[dict]]:
    day = HISTORY_DIR / date
    analysis = _load_gz(day / "analysis.json.gz")
    nav = _load_gz(day / "nav.json.gz")
    news = _load_gz(day / "news.json.gz")
    return analysis, {n["fund_code"]: n for n in nav}, news


def _returns_html(fund_code: str, nav_by_code: dict[str, dict]) -> str:
    nav = nav_by_code.get(fund_code)
    if not nav:
        return "-"
    parts = []
    for label, key in _PERIODS:
        parts.append(f"{label} {_esc(nav.get("returns", {}).get(key, "-"))}%")
    return "　".join(parts)


def _trend_mini_table(points: list[TrendPoint]) -> str:
    rows = "".join(
        f"<tr><td>{_esc(p.date[5:])}</td>"
        f"<td class=\"num\">{_esc(f'{p.preliminary_score:.0f}')}</td>"
        f"<td class=\"num\">{_esc(p.rank)}</td>"
        f"<td class=\"num\">{_esc(f'{p.value_score:.0f}' if p.value_score is not None else '—')}</td></tr>"
        for p in points
    )
    return (
        '<table class="mini"><thead><tr><th>日期</th><th>初評分</th><th>排名</th>'
        "<th>深度分數</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _trend_block(fund_code: str, series: dict[str, list[TrendPoint]] | None) -> str:
    """個案卡片內的近期趨勢區塊（sparkline + 迷你表）。資料不足時回傳累積中提示。"""
    if not series:
        return ""
    pts = series_for(fund_code, series)
    if len(pts) < 2:
        return (
            '<div class="blk trend-blk"><h4>📈 近期趨勢</h4>'
            '<span class="trend-note">歷史資料累積中（需 ≥2 個交易日，每日排程自動累積）</span></div>'
        )
    s_score = sparkline_svg(pts, "preliminary_score", label="初評分")
    s_rank = sparkline_svg(pts, "rank", label="排名")
    if not s_score or not s_rank:
        return ""
    st = trend_stats(pts, "preliminary_score")
    st_r = trend_stats(pts, "rank")
    stats_line = (
        f"初 {st['first']:.0f} → 末 {st['last']:.0f}"
        f"（{'▲' if st['delta'] >= 0 else '▼'}{abs(st['delta']):.1f}）"
        f"・高 {st['max']:.0f}／低 {st['min']:.0f}／均 {st['avg']:.0f}"
    )
    rank_line = f"排名區間 {st_r['max']}–{st_r['min']}"
    # 深度分數（value_score）為稀疏序列：僅在 ≥2 個交易日有深度分析時顯示
    s_value = sparkline_svg(pts, "value_score", label="深度分數")
    value_block = ""
    if s_value:
        st_v = trend_stats(pts, "value_score")
        value_block = (
            '<span class="trend-metric">深度分數（僅深度分析日）</span>' + s_value
            + f'<div class="trend-stats">初 {st_v["first"]:.0f} → 末 {st_v["last"]:.0f}'
            f'（{"▲" if st_v["delta"] >= 0 else "▼"}{abs(st_v["delta"]):.1f}）'
            f"・高 {st_v['max']:.0f}／低 {st_v['min']:.0f}／均 {st_v['avg']:.0f}</div>"
        )
    return (
        '<div class="blk trend-blk"><h4>📈 近期趨勢（近 '
        f"{len(pts)} 日）</h4>"
        '<span class="trend-metric">初評分</span>' + s_score
        + '<span class="trend-metric">排名（倒序，越低越好）</span>' + s_rank
        + value_block
        + f'<div class="trend-stats">{_esc(stats_line)}<br>{_esc(rank_line)}</div>'
        + _trend_mini_table(pts[-5:])
        + "</div>"
    )


def _comparison_section(
    analysis: dict,
    series: dict[str, list[TrendPoint]] | None,
    window: int,
) -> str:
    """首頁「趨勢比較」：前段（深度分析）基金 × 最近 N 交易日的排名並排表 + 評分表。"""
    if not series:
        return ""
    dates = sorted({p.date for pts in series.values() for p in pts})
    if len(dates) < 2:
        return (
            '<h2>📊 趨勢比較（多日並排）</h2>'
            '<p class="trend-note">歷史資料累積中：需 ≥2 個交易日，每日排程將自動累積。</p>'
        )
    funds = [f for f in analysis.get("funds", []) if f.get("deep_analysis")]
    if not funds:
        return ""
    top_codes = [f["fund_code"] for f in funds]
    names = {f["fund_code"]: f["name"] for f in funds}
    data = comparison_data(series, top_codes, window, names=names, dates=dates)
    cmp_dates = list(data["dates"])

    def cell(code: str, date: str) -> str:
        p = next((x for x in series.get(code, []) if x.date == date), None)
        if p is None:
            return '<td class="cmp-miss">—</td>'
        tip = f"title=\"初評分 {p.preliminary_score:.0f}"
        if p.overall_rating:
            tip += f"・{p.overall_rating}"
        tip += '"'
        return f'<td class="cmp-rank" {tip}>{p.rank}</td>'

    def score_cell(code: str, date: str) -> str:
        p = next((x for x in series.get(code, []) if x.date == date), None)
        if p is None:
            return '<td class="cmp-miss">—</td>'
        return f'<td class="cmp-rank">{p.preliminary_score:.0f}</td>'

    head_cells = "".join(
        f'<th class="cmp-rank" title="{_esc(d)}">{_esc(d[5:])}</th>' for d in cmp_dates
    )
    rows = []
    score_rows = []
    for f in funds:
        code = f["fund_code"]
        name = f"<td><a href=\"#fund-{_esc(code)}\">{_esc(f['name'])}</a></td>"
        rows.append(
            f"<tr>{name}" + "".join(cell(code, d) for d in cmp_dates)
            + _rank_delta_cell(code, series) + _rank_spark_cell(code, series)
            + "</tr>"
        )
        score_rows.append(
            f"<tr>{name}" + "".join(score_cell(code, d) for d in cmp_dates) + "</tr>"
        )
    rank_table = (
        '<table class="cmp"><thead><tr><th>基金</th>'
        + head_cells
        + "<th>近窗變化</th><th>排名趨勢</th></tr></thead>"
        + f"<tbody>{''.join(rows)}</tbody></table>"
    )
    score_table = (
        '<table class="cmp"><thead><tr><th>基金</th>' + head_cells + "</tr></thead>"
        + f"<tbody>{''.join(score_rows)}</tbody></table>"
    )

    return (
        f'<h2>📊 趨勢比較（近 {len(cmp_dates)} 日）</h2>'
        '<p class="trend-note">欄位＝當日排名（將滑鼠移到數字可看當日初評分與評級）；'
        '「近窗變化」為視窗首日→末日排名變動（▲ 上升）。</p>'
        f'<div class="cmp-scroll">{rank_table}</div>'
        '<details><summary><span class="g">▶</span> 展開／收合 初評分並排表</summary>'
        f'<div class="cmp-scroll">{score_table}</div></details>'
    )


def _rank_delta_cell(
    code: str, series: dict[str, list[TrendPoint]]
) -> str:
    pts = series.get(code, [])
    first, last = (pts[0].rank, pts[-1].rank) if len(pts) >= 2 else (None, None)
    if first is None or last is None:
        return '<td class="cmp-rank">—</td>'
    d = last - first
    if abs(d) >= RANK_JUMP_THRESHOLD:
        # 大幅跳動：高亮（大升 .jump-up / 大降 .jump-down）
        if d < 0:
            return f'<td class="cmp-rank"><span class="jump-up">▲{abs(d)}</span></td>'
        return f'<td class="cmp-rank"><span class="jump-down">▼{d}</span></td>'
    if d == 0:
        label, cls = "持平", "sent-u"
    elif d < 0:
        label, cls = f"▲{abs(d)}", "sent-p"
    else:
        label, cls = f"▼{d}", "sent-n"
    return f'<td class="cmp-rank"><span class="{cls}">{label}</span></td>'


def _rank_spark_cell(
    code: str, series: dict[str, list[TrendPoint]]
) -> str:
    pts = series.get(code, [])
    spark = sparkline_svg(pts, "rank", width=120, height=34, label="排名")
    return f"<td>{spark}</td>"


def _fund_news_list(fa: dict, news: list[dict] | None, limit: int = 5) -> list[dict]:
    """與基金相關之新聞（WP3 分層：基金特定優先，無則系列 fallback）。"""
    if not news:
        return []
    fund = Fund(fund_code=fa.get("fund_code", ""), name=fa.get("name", ""))
    specific = [n for n in news if fund_matches_title(fund, n.get("title") or "")]
    pool = specific or [
        n for n in news if fund_matches_series(fund, n.get("title") or "")
    ]
    return pool[:limit]


def _detail_card(
    fa: dict,
    nav_by_code: dict[str, dict],
    series: dict[str, list[TrendPoint]] | None = None,
    news: list[dict] | None = None,
) -> str:
    da = fa.get("deep_analysis") or {}
    name = fa["name"]
    rating = da.get("overall_rating") or "-"
    sentiment = da.get("market_sentiment") or "-"
    sent_cls = {"Positive": "sent-p", "Negative": "sent-n"}.get(sentiment, "sent-u")
    nav = nav_by_code.get(fa["fund_code"], {})
    score = da.get("value_score")
    score_txt = f"{score:.0f}" if score is not None else "-"
    search = _esc(f"{fa['name']} {fa['fund_code']}".lower())

    pb = fa.get("preliminary_breakdown") or {}
    prelim_detail = (
        f"<br>初評分細項：成長品質 {pb.get('growth_score', '-')}"
        f" ｜ 穩定持續 {pb.get('stability_score', '-')}"
        f" ｜ 新聞聲量 {pb.get('news_score', '-')}"
    )
    dca_ret = pb.get("dca_return_pct") or 0.0
    dca_bonus = pb.get("dca_bonus") or 0.0
    if dca_ret and dca_ret != 0:
        prelim_detail += f" ｜ DCA年報酬 {dca_ret:.1f}%（推估，+{dca_bonus:.1f}）"
    income_cls = income_class_from_name(fa.get("name", ""))
    income_suit = da.get("income_suitability") or ""
    eff_yield = pb.get("effective_yield_pct") or 0.0
    raw_yield = pb.get("yield_pct") or 0.0
    quality = pb.get("income_quality") or 0.0
    risk_level = pb.get("risk_level") or ""
    income_tag = f"<br>收益取向：{income_cls}"
    if risk_level:
        income_tag += f" ｜ 風險等級 {_esc(risk_level)}"
    if eff_yield and eff_yield > 0:
        income_tag += f" ｜ 近12M配息率 {eff_yield:.2f}%"
        if quality < 1:
            income_tag += f"（名目 {raw_yield:.2f}% ／收益占比 {quality * 100:.0f}%）"
    if income_suit:
        income_tag += f" ｜ 被動收入適合度：{income_suit}"

    rel_news = _fund_news_list(fa, news)
    if rel_news:
        lis = "".join(
            f'<li><a href="{_esc(n.get("url", ""))}" target="_blank" rel="noopener">'
            f"{_esc(n.get('title', ''))}</a> "
            f'<small>{_esc(n.get("source", ""))} · {_esc(n.get("published_at", ""))}</small></li>'
            for n in rel_news
        )
        news_html = (
            f'<div class="blk"><h4>相關新聞來源</h4><ul class="news-src">{lis}</ul></div>'
        )
    else:
        news_html = ""

    return f"""<details id="fund-{_esc(fa['fund_code'])}" data-ch="{_esc(','.join(fa.get('channels', [])))}" data-search="{search}">
<summary><span class="g">#{fa['rank']}</span>{_esc(name)}
<span class="code-sum">{_esc(fa['fund_code'])}</span>
　<span class="rating r-{_esc(rating)}">{_esc(rating)}</span>
 <span class="num">深度分數 {score_txt} · 初評分 {fa['preliminary_score']}</span>
 {_channel_badges(fa.get('channels') or [])}</summary>
<div class="f-body">
<div class="col">
<div class="blk"><h4>淨值資訊</h4>淨值 {_esc(nav.get("nav", "-"))}（{_esc(nav.get("nav_date", "-"))}）<br>
期間報酬：{_returns_html(fa['fund_code'], nav_by_code)}<br>
通路：{_esc("、".join(fa.get("channels", [])) or "-")}{prelim_detail}{income_tag}</div>
{_trend_block(fa['fund_code'], series)}
<div class="blk"><h4>市場情緒</h4><span class="{sent_cls}">{_esc(sentiment)}</span>
<h4>購入模式</h4>{_esc(da.get("recommended_strategy", "-"))}<br>
{_esc(da.get("strategy_explanation", ""))}</div>
<div class="blk"><h4>新聞摘要</h4><ul>
{''.join(f"<li>{_esc(x)}</li>" for x in da.get("news_summary") or []) or '<li>無相關新聞</li>'}</ul>
<h4>評分理由</h4>{_esc(da.get("score_rationale", ""))}</div>
{news_html}
<div class="blk"><h4>優勢</h4><ul>{''.join(f"<li>{_esc(p)}</li>" for p in da.get("pros") or [])}</ul>
<h4>劣勢 / 風險</h4><ul>{''.join(f"<li>{_esc(c)}</li>" for c in da.get("cons") or [])}</ul></div>
</div>
<div class="tax">🏷️ 稅務標籤：境外所得（最低稅負制）｜免扣 2.11% 二代健保｜享 750 萬免稅額、100 萬免申報門檻</div>
</div></details>"""


def _ranking_rows(analysis: dict, nav_by_code: dict[str, dict], limit: int = 0) -> str:
    rows = []
    for i, fa in enumerate(analysis.get("funds", [])):
        if limit and i >= limit:
            break
        ch = ",".join(fa.get("channels", []))
        search = _esc(f"{fa['name']} {fa['fund_code']}".lower())
        eff_yield = (fa.get("preliminary_breakdown") or {}).get("effective_yield_pct") or 0.0
        quality = (fa.get("preliminary_breakdown") or {}).get("income_quality") or 0.0
        yield_tag = ""
        if eff_yield and eff_yield > 0:
            yield_tag = f'<span class="yield-tag">配息率 {eff_yield:.2f}%'
            if quality < 1:
                yield_tag += f'<small>（收益{quality * 100:.0f}%）</small>'
            yield_tag += "</span>"
        risk_level = (fa.get("preliminary_breakdown") or {}).get("risk_level") or ""
        rr_tag = f'<span class="rr-tag">{_esc(risk_level)}</span>' if risk_level else ""
        rows.append(
            f"<tr data-ch=\"{_esc(ch)}\" data-search=\"{search}\">"
            f"<td class=\"num\">{fa['rank']}</td>"
            f"<td class=\"rank-name\"><a href=\"#fund-{_esc(fa['fund_code'])}\">{_esc(fa['name'])}</a>"
            f"<span class=\"code\">{_esc(fa['fund_code'])}</span>{rr_tag}{yield_tag}</td>"
            f"<td class=\"num\">{fa['preliminary_score']}</td>"
            f"<td>{_channel_badges(fa.get('channels') or [])}</td></tr>"
        )
    return "".join(rows)


CHANNEL_JS = """<script>
(function(){
  window._ch = 'all';
  window._q = '';
  var sel = function(s){ return Array.prototype.slice.call(document.querySelectorAll(s)); };
  function matches(el){
    if (window._ch !== 'all') {
      var chs = (el.getAttribute('data-ch')||'').split(',');
      if (chs.indexOf(window._ch) < 0) return false;
    }
    var q = window._q;
    if (!q) return true;
    return (el.getAttribute('data-search')||'').toLowerCase().indexOf(q) >= 0;
  }
  window.applyFilters = function(){
    sel('tr[data-search]').forEach(function(tr){ tr.style.display = matches(tr) ? '' : 'none'; });
    sel('details[data-search]').forEach(function(d){ d.style.display = matches(d) ? '' : 'none'; });
  };
  window.setChannel = function(c){
    window._ch = c;
    applyFilters();
    sel('.ch-chip').forEach(function(b){ b.classList.toggle('active', b.getAttribute('data-c')===c); });
  };
  window.setSearch = function(q){
    window._q = (q||'').toLowerCase().trim();
    applyFilters();
  };
})();
</script>"""


def _rank_toolbar_html(
    funds: list[dict], limit: int = 0, show_channel: bool = True
) -> str:
    """排名工具列：搜尋框（名稱/代號）+ 可選通路篩選。"""
    parts = [
        '<input type="search" class="rank-search" placeholder="🔍 搜尋名稱或代號" '
        'aria-label="搜尋名稱或代號" oninput="setSearch(this.value)">'
    ]
    if show_channel:
        rows = funds[:limit] if limit else funds
        counts: dict[str, int] = {}
        for f in rows:
            for c in f.get("channels", []):
                counts[c] = counts.get(c, 0) + 1
        chips = [
            f'<button type="button" class="ch-chip active" data-c="all" '
            f'onclick="setChannel(\'all\')">全部 <b>{len(rows)}</b></button>'
        ]
        for c in CHANNELS:
            if c in counts:
                chips.append(
                    f'<button type="button" class="ch-chip" data-c="{_esc(c)}" '
                    f'onclick="setChannel(\'{_esc(c)}\')">{_esc(c)} <b>{counts[c]}</b></button>'
                )
        parts.append(
            '<span class="ch-filters" role="group" aria-label="銷售通路篩選">'
            '<span class="ch-label">通路：</span>' + "".join(chips) + "</span>"
        )
    return '<div class="rank-toolbar">' + "".join(parts) + "</div>" + CHANNEL_JS


def _channel_stats(analysis: dict, limit: int) -> dict[str, int]:
    """排名清單內每通路總數（含跨通路上架之基金；三者加總可能 > 清單數）。"""
    counts = {c: 0 for c in CHANNELS}
    funds = analysis.get("funds", [])
    rows = funds[:limit] if limit else funds
    for fa in rows:
        for c in CHANNELS:
            if c in (fa.get("channels") or []):
                counts[c] += 1
    return counts


def _channel_dist_html(stats: dict[str, int], limit: int) -> str:
    parts = " ｜ ".join(
        f"{_esc(name)} <b>{stats[name]}</b>" for name in CHANNELS
    )
    return (
        f'<p class="ch-dist">通路（排名清單 {limit} 內）：{parts}'
        f"</p>"
    )


# 通路 icon：單字 + 品牌色
_CHANNEL_ICON: dict[str, tuple[str, str]] = {
    "元大證券": ("元", "#C8102E"),
    "匯豐銀行": ("匯", "#0072CE"),
    "渣打銀行": ("渣", "#00536D"),
}


def _channel_badges(channels: list[str]) -> str:
    """靠右通路 icon（內嵌 SVG monogram + 懸停全名）。"""
    if not channels:
        return ""
    icons = "".join(
        _channel_icon(name) for name in CHANNELS if name in (channels or [])
    )
    return f'<span class="ch-badges">{icons}</span>'


def _channel_icon(name: str) -> str:
    char, color = _CHANNEL_ICON.get(name, ("?", "#6b7280"))
    return (
        f'<span class="ch-icon" title="{_esc(name)}" aria-label="{_esc(name)}">'
        f'<svg width="18" height="18" viewBox="0 0 18 18" role="img">'
        f'<rect width="18" height="18" rx="4" fill="{color}"/>'
        f'<text x="9" y="12.5" text-anchor="middle" font-size="11" '
        f'fill="#fff" font-weight="600">{char}</text></svg></span>'
    )


def render_report(
    analysis: dict,
    nav_by_code: dict[str, dict],
    date: str,
    compact: bool = False,
    calendar_html: str = "",
    nav_html: str = "",
    series: dict[str, list[TrendPoint]] | None = None,
    trend_window: int = DEFAULT_WINDOW,
    rank_limit: int | None = None,
    show_channel_filter: bool = False,
    news: list[dict] | None = None,
) -> str:
    now = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M")
    funds = analysis.get("funds", [])
    total = len(funds)
    deep_count = analysis.get("deep_analyzed_count", 0)
    scored = [f for f in funds if f.get("deep_analysis")]

    detail_cards = "".join(
        _detail_card(f, nav_by_code, series if not compact else None, news)
        for f in funds
        if f.get("deep_analysis")
    ) or "<p>（本日無深度分析資料）</p>"
    comparison = (
        "" if compact else _comparison_section(analysis, series, trend_window)
    )

    if compact:
        # 精簡版（archive 歷史頁）：與首頁一致顯示前 INDEX_RANK_LIMIT 名
        limit = INDEX_RANK_LIMIT
        rank_label = (
            f"前 {limit} 名排名（完整排名見 "
            '<a href="../ranking.html" style="color:var(--brand)">ranking.html</a>）'
        )
    elif rank_limit is not None:
        limit = rank_limit
        rank_label = (
            f"前 {limit} 名排名（完整排名見 "
            '<a href="ranking.html" style="color:var(--brand)">ranking.html</a>）'
        )
    else:
        limit = 0
        rank_label = f"完整排名表（{total} 檔）"

    toolbar_html = (
        _rank_toolbar_html(
            funds, limit, show_channel=(show_channel_filter and not compact)
        )
        if limit
        else ""
    )
    channel_dist_html = (
        _channel_dist_html(_channel_stats(analysis, limit), limit)
        if limit
        else ""
    )
    rank_rows = _ranking_rows(analysis, nav_by_code, limit=limit)

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AlphaFund-Daily 每日報告｜{_esc(date)}</title>
<style>{CSS}</style>
</head>
<body>
{nav_html}
<div class="wrap">
<header>
<h1>AlphaFund-Daily 每日境外基金投研報告</h1>
<div class="meta">報告日期：{_esc(date)} ｜ 頁面生成：{_esc(now)}（Asia/Taipei）</div>
</header>

{calendar_html}

<div class="stat-row">
<div class="stat"><b>{limit}</b><span>排名清單（全體 {total} 檔）</span></div>
<div class="stat"><b>{deep_count}</b><span>深度分析檔數</span></div>
<div class="stat"><b>{len(scored)}</b><span>已產生 AI 評級</span></div>
</div>

{channel_dist_html}

<h2>基金排名</h2>
<p style="font-size:13px;color:var(--mut)">依 AI 初評分（動能 + 新聞聲量）排序；前段基金另有 LLM 深度分析。</p>
{toolbar_html}
<details>
<summary><span class="g">▶</span> 展開／收合{rank_label}</summary>
<div style="max-height:480px;overflow:auto;border-radius:8px">
<table class="rank">
<thead><tr><th>#</th><th>基金名稱</th><th class="num">初評分</th><th>通路</th></tr></thead>
<tbody>{rank_rows}</tbody>
</table></div>
</details>

<h2>個案深度解讀（前 {deep_count} 名）</h2>
{detail_cards}

{comparison}

<h2>稅務說明</h2>
<div class="tax" style="margin-top:0">
本專案標的皆為境外基金（非 TW 註冊），資本利得與配息 100% 歸類為「海外所得」：
<ul>
<li>100 萬免申報門檻：全戶全年海外所得未達新臺幣 100 萬元，無須計入基本所得額。</li>
<li>750 萬免稅額：合併其他基本所得額後，享每年 750 萬元免稅額度。</li>
<li>免二代健保：境外基金配息免扣取 2.11% 二代健保補充保費。</li>
</ul>
</div>

<footer>
<p><b>免責聲明：</b>本報告由自動化程式與 AI 模型（LLM 供應商鏈）生成，僅供學術研究與個人資產管理參考，不構成任何投資招攬、要約或決策依據。投資人應獨立判斷並審慎評估風險；過去績效不代表未來績效保證。</p>
<p>資料來源：TDCC 基金資訊觀測站（上架清單／淨值／績效）、Google News（新聞）。資料可能延遲或不完整。</p>
</footer>
</div>
</body>
</html>"""


def generate_report(date: str, out_file: Path | None = None) -> Path:
    analysis, nav_by_code, news = load_report_data(date)
    series = build_time_series()
    html_out = render_report(
        analysis,
        nav_by_code,
        date,
        series=series,
        rank_limit=INDEX_RANK_LIMIT,
        show_channel_filter=True,
        news=news,
    )
    path = out_file or REPORT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_out, encoding="utf-8")
    return path


def _render_archive_page(date: str, dates: list[str]) -> str:
    analysis, nav_by_code, news = load_report_data(date)
    return render_report(
        analysis,
        nav_by_code,
        date,
        compact=True,
        calendar_html=_calendar_panel(dates, date, base=""),
        nav_html=_navbar_html(is_latest=False, date=date),
        news=news,
    )


def generate_archive(docs_dir: Path | None = None) -> tuple[Path, list[Path]]:
    """重產全部歷史 archive 頁 + docs/index.html（最新完整報告 + 月曆）。

    - archive/<YYYY-MM-DD>.html：精簡版報告 + 月曆（歷史瀏覽）。
    - index.html：最新完整報告 + 月曆（預設顯示最新）。
    - trends.html：趨勢比較頁（隨同更新）。
    """
    docs_dir = docs_dir or PROJECT_ROOT / "docs"
    archive_dir = docs_dir / "archive"
    dates = _available_dates()
    if not dates:
        raise FileNotFoundError("data/history 下無可生成之分析資料")

    series = build_time_series()

    pages: list[Path] = []
    for date in dates:
        page = archive_dir / f"{date}.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(_render_archive_page(date, dates), encoding="utf-8")
        pages.append(page)

    latest = dates[-1]
    analysis, nav_by_code, news = load_report_data(latest)
    index = docs_dir / "index.html"
    index.write_text(
        render_report(
            analysis,
            nav_by_code,
            latest,
            compact=False,
            calendar_html=_calendar_panel(dates, latest, base="archive/"),
            nav_html=_navbar_html(is_latest=True, date=latest),
            series=series,
            rank_limit=INDEX_RANK_LIMIT,
            show_channel_filter=True,
            news=news,
        ),
        encoding="utf-8",
    )
    generate_trends(docs_dir=docs_dir, series=series)
    generate_ranking(docs_dir=docs_dir)
    from .health import generate_health

    generate_health(docs_dir=docs_dir)
    return index, pages


def _render_ranking_page(
    analysis: dict,
    nav_by_code: dict[str, dict],
    date: str,
    nav_html: str,
) -> str:
    """完整排名頁（最新全列 + 搜尋/通路 filter）。"""
    now = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M")
    funds = analysis.get("funds", [])
    filter_html = _rank_toolbar_html(funds, 0, show_channel=True)
    rank_rows = _ranking_rows(analysis, nav_by_code, limit=0)
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AlphaFund-Daily 完整排名｜{_esc(date)}</title>
<style>{CSS}</style>
</head>
<body>
{nav_html}
<div class="wrap">
<header>
<h1>🏆 完整排名表</h1>
<div class="meta">報告日期：{_esc(date)} ｜ 全體 {len(funds)} 檔（三通路 × USD）｜ 頁面生成：{_esc(now)}（Asia/Taipei）</div>
</header>
<p style="font-size:13px;color:var(--mut)">依 AI 初評分（動能 + 新聞聲量）排序之完整排名；點通路可篩選上架通路。</p>
{filter_html}
<div style="max-height:70vh;overflow:auto;border-radius:8px">
<table>
<thead><tr><th>#</th><th>基金名稱</th><th class="num">初評分</th><th>通路</th></tr></thead>
<tbody>{rank_rows}</tbody>
</table></div>
<footer>
<p><b>免責聲明：</b>本表由自動化程式與 AI 模型（LLM 供應商鏈）生成，僅供學術研究與個人資產管理參考，不構成任何投資招攬、要約或決策依據。</p>
</footer>
</div>
</body>
</html>"""


def generate_ranking(docs_dir: Path | None = None) -> Path:
    """生成 docs/ranking.html（最新完整排名表，僅覆寫一份）。"""
    docs_dir = docs_dir or PROJECT_ROOT / "docs"
    dates = _available_dates()
    if not dates:
        raise FileNotFoundError("data/history 下無可生成之分析資料")
    latest = dates[-1]
    analysis, nav_by_code, news = load_report_data(latest)
    nav_html = _navbar_html(
        is_latest=True, date=latest, active="ranking", show_calendar=False
    )
    path = docs_dir / "ranking.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _render_ranking_page(analysis, nav_by_code, latest, nav_html), encoding="utf-8"
    )
    return path


def _trends_navbar_html() -> str:
    """趨勢頁固定頂部導覽列（日曆面板位於最新報告頁）。"""
    return (
        '<nav class="navbar"><div class="nav-inner">'
        '<span class="brand">AlphaFund-Daily</span>'
        '<span class="nav-links">'
        '<a href="index.html">最新報告</a>'
        '<a href="ranking.html">🏆 完整排名</a>'
        '<a class="active" href="trends.html">📈 趨勢</a>'
        '<a href="health.html">🩺 系統健康</a>'
        "</span></div></nav>"
    )


def _render_trends_page(
    series: dict[str, list[TrendPoint]],
    dates: list[str],
    nav_html: str,
) -> str:
    """趨勢比較頁：前段基金之較大趨勢圖 + 多日比較表 + 區間統計。"""
    now = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M")
    if len(dates) < 2:
        body = (
            '<div class="wrap"><header><h1>📈 趨勢比較</h1>'
            '<div class="meta">趨勢頁隨每日排程自動累積；目前歷史僅 '
            f'{len(dates)} 個交易日，需 ≥2 日才產生圖表。</div></header>'
            '<p class="trend-note">請於第二個交易日後重新檢視。</p></div>'
        )
        return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AlphaFund-Daily 趨勢比較</title>
<style>{CSS}</style></head>
<body>{nav_html}{body}</body></html>"""

    latest_analysis, _, _ = load_report_data(dates[-1])
    top = [f for f in latest_analysis.get("funds", []) if f.get("deep_analysis")]
    if not top:
        body = '<div class="wrap"><p class="trend-note">目前無深度分析基金可顯示趨勢。</p></div>'
        return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AlphaFund-Daily 趨勢比較</title>
<style>{CSS}</style></head>
<body>{nav_html}{body}</body></html>"""

    cards = []
    for f in top:
        code = f["fund_code"]
        pts = series_for(code, series)
        if len(pts) < 2:
            continue
        s_score = sparkline_svg(pts, "preliminary_score", width=560, height=150, label="初評分")
        s_rank = sparkline_svg(pts, "rank", width=560, height=150, label="排名")
        s_value = sparkline_svg(pts, "value_score", width=560, height=150, label="深度分數")
        st = trend_stats(pts, "preliminary_score")
        st_r = trend_stats(pts, "rank")
        rating = (f.get("deep_analysis") or {}).get("overall_rating") or "-"
        date_txt = "、".join(p.date[5:] for p in pts)
        value_chart = ""
        if s_value:
            st_v = trend_stats(pts, "value_score")
            value_chart = (
                f'<div class="trend-chart"><h4>深度分數（僅深度分析日；{st_v["first"]:.0f} → '
                f'{st_v["last"]:.0f}，{"▲" if st_v["delta"] >= 0 else "▼"}{abs(st_v["delta"]):.1f}）</h4>'
                f"{s_value}</div>"
            )
        cards.append(
            f'<div class="trend-hero"><h3>#{f["rank"]} {_esc(f["name"])}'
            f' <span class="rating r-{_esc(rating)}">{_esc(rating)}</span></h3>'
            f'<div class="sub">{_esc(f["fund_code"])} ｜ 近 {len(pts)} 個交易日（{_esc(date_txt)}）</div>'
            '<div class="trend-charts">'
            f'<div class="trend-chart"><h4>初評分（{st["first"]:.0f} → {st["last"]:.0f}'
            f'，{"▲" if st["delta"] >= 0 else "▼"}{abs(st["delta"]):.1f}）</h4>{s_score}</div>'
            f'<div class="trend-chart"><h4>排名（倒序，越低越好；區間 {st_r["max"]}–{st_r["min"]}）</h4>{s_rank}</div>'
            f"{value_chart}"
            "</div>"
            f'<div class="trend-stats">區間：初 {st["first"]:.0f} → 末 {st["last"]:.0f}'
            f' ｜ 高 {st["max"]:.0f} ／ 低 {st["min"]:.0f} ／ 平均 {st["avg"]:.0f}'
            f' ｜ 排名區間 {st_r["max"]}–{st_r["min"]}</div>'
            + _trend_mini_table(pts[-10:])
            + "</div>"
        )
    if not cards:
        cards = ['<p class="trend-note">歷史資料尚不足 2 個交易日。</p>']

    body = (
        '<div class="wrap"><header><h1>📈 趨勢比較</h1>'
        f'<div class="meta">資料範圍：{_esc(dates[0])} – {_esc(dates[-1])}'
        f'（{len(dates)} 個交易日）｜ 頁面生成：{_esc(now)}（Asia/Taipei）</div></header>'
        '<p style="font-size:13px;color:var(--mut)">以下為最近一次深度分析之基金，'
        '顯示其歷史初評分與排名走勢；每日排程自動累積新點。</p>'
        + "".join(cards)
        + f'<footer><p><b>免責聲明：</b>趨勢圖僅反映歷史統計，過去績效不代表未來績效保證。</p></footer></div>'
    )
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AlphaFund-Daily 趨勢比較</title>
<style>{CSS}</style></head>
<body>{nav_html}{body}</body></html>"""


def generate_trends(
    docs_dir: Path | None = None,
    series: dict[str, list[TrendPoint]] | None = None,
) -> Path:
    """生成 docs/trends.html（趨勢比較頁）。"""
    docs_dir = docs_dir or PROJECT_ROOT / "docs"
    series = series if series is not None else build_time_series()
    dates = load_all_dates()
    nav_html = _trends_navbar_html()
    path = docs_dir / "trends.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_trends_page(series, dates, nav_html), encoding="utf-8")
    return path
