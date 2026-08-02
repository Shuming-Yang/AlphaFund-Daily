"""每日健康監控：彙整各日管線執行狀態與 LLM 供應商使用分布。

產出 docs/health.html：
- 摘要統計（歷史天數、最新日期、深度分析完成率、供應商數）。
- 每日表格：日期｜基金數｜深度分析｜跳過/錯誤｜供應商分布｜新聞數。
- 供應商使用彙總（跨日期）。
"""
from __future__ import annotations

import gzip
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import HISTORY_DIR, PROJECT_ROOT, TIMEZONE

HEALTH_FILE = PROJECT_ROOT / "docs" / "health.html"

_HEALTH_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1a1d21;--mut:#6b7280;--line:#e5e7eb;
--brand:#0b5b8c;--pos:#0a7a3d;--neg:#b02a2a;}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Noto Sans TC","PingFang TC",sans-serif;
background:var(--bg);color:var(--ink);line-height:1.6}
.wrap{width:min(96%,1280px);margin:0 auto;padding:24px 16px 48px}
.navbar{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.96);backdrop-filter:blur(6px);
border-bottom:1px solid var(--line)}
.nav-inner{width:min(96%,1280px);margin:0 auto;display:flex;align-items:center;justify-content:space-between;
padding:10px 16px;flex-wrap:wrap;row-gap:6px}
.brand{font-weight:700;color:var(--brand);font-size:15px}
.nav-links{display:flex;align-items:center;gap:4px;flex-wrap:wrap}
.nav-links a{color:var(--mut);text-decoration:none;font-size:13px;padding:5px 10px;border-radius:6px;white-space:nowrap}
.nav-links a:hover{background:#eef1f4;color:var(--ink)}
.nav-links a.active{background:var(--brand);color:#fff;font-weight:600}
header h1{font-size:22px;margin:0 0 4px;color:var(--brand)}
header .meta{color:var(--mut);font-size:13px}
.stat-row{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 16px;min-width:120px}
.stat b{font-size:20px;display:block}
.stat span{font-size:12px;color:var(--mut)}
h2{font-size:16px;margin:28px 0 10px;border-left:4px solid var(--brand);padding-left:8px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:8px}
th,td{text-align:left;padding:7px 10px;font-size:13px;border-bottom:1px solid var(--line)}
th{background:#eef1f4}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.ok{color:var(--pos);font-weight:600}
.bad{color:var(--neg);font-weight:600}
.scroll{overflow-x:auto;border-radius:8px}
footer{margin-top:36px;border-top:1px solid var(--line);padding-top:14px;font-size:12px;color:var(--mut)}
@media (max-width:640px){.f-body .col{grid-template-columns:1fr}}
"""


def _load_gz(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def build_health_data() -> list[dict]:
    """依 data/history/* 彙整每日健康資料。"""
    entries: list[dict] = []
    for date in sorted(
        d.name for d in HISTORY_DIR.glob("????-??-??") if d.is_dir()
    ):
        day = HISTORY_DIR / date
        if not (day / "analysis.json.gz").exists():
            continue
        an = _load_gz(day / "analysis.json.gz")
        funds = an.get("funds", [])
        statuses = Counter(f.get("status") for f in funds)
        providers = Counter(
            f.get("provider")
            for f in funds
            if f.get("status") == "deep_analyzed" and f.get("provider")
        )
        news = 0
        snap_path = day / "snapshot.json.gz"
        if snap_path.exists():
            snap = _load_gz(snap_path)
            news = len(snap.get("news", []))
        entries.append(
            {
                "date": date,
                "universe": len(funds),
                "deep": an.get("deep_analyzed_count", 0),
                "quota_skipped": statuses.get("quota_skipped", 0),
                "error": statuses.get("error", 0),
                "providers": dict(providers),
                "news": news,
            }
        )
    return entries


def _esc(value: object) -> str:
    import html as html_mod

    return html_mod.escape(str(value if value is not None else ""), quote=True)


def render_health_page(entries: list[dict], nav_html: str) -> str:
    now = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M")
    total_days = len(entries)
    latest = entries[-1] if entries else None
    latest_date = latest["date"] if latest else "—"

    # 摘要統計
    deep_total = sum(e["deep"] for e in entries)
    err_total = sum(e["error"] + e["quota_skipped"] for e in entries)
    provider_agg: Counter[str] = Counter()
    for e in entries:
        provider_agg.update(e["providers"])
    provider_count = len(provider_agg)

    stats = (
        f'<div class="stat"><b>{total_days}</b><span>歷史交易日</span></div>'
        f'<div class="stat"><b>{latest_date}</b><span>最新報告日期</span></div>'
        f'<div class="stat"><b>{deep_total}</b><span>累計深度分析</span></div>'
        f'<div class="stat"><b>{err_total}</b><span>跳過/錯誤總數</span></div>'
        f'<div class="stat"><b>{provider_count}</b><span>使用過之 LLM 供應商</span></div>'
    )

    # 每日表格
    rows = []
    for e in entries:
        prov = "、".join(f"{k}×{v}" for k, v in sorted(e["providers"].items())) or "—"
        skip_bad = (
            e["quota_skipped"] or e["error"]
        )
        deep_cell = (
            f'<span class="ok">{e["deep"]}</span>'
            if not skip_bad
            else f'<span class="bad">{e["deep"]}</span>'
        )
        rows.append(
            f"<tr><td>{e['date']}</td>"
            f'<td class="num">{e["universe"]}</td>'
            f"<td class=\"num\">{deep_cell}</td>"
            f'<td class="num">{e["quota_skipped"]}</td>'
            f'<td class="num">{e["error"]}</td>'
            f"<td>{_esc(prov)}</td>"
            f'<td class="num">{e["news"]}</td></tr>'
        )
    daily_table = (
        '<table><thead><tr><th>日期</th><th class="num">基金數</th>'
        '<th class="num">深度分析</th><th class="num">跳過</th><th class="num">錯誤</th>'
        "<th>供應商分布</th><th class=\"num\">新聞數</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )

    # 供應商彙總
    provider_rows = "".join(
        f"<tr><td>{_esc(k)}</td><td class=\"num\">{v}</td></tr>"
        for k, v in provider_agg.most_common()
    ) or "<tr><td colspan=\"2\">（無深度分析）</td></tr>"
    provider_table = (
        '<table><thead><tr><th>LLM 供應商</th><th class="num">深度分析次數</th></tr></thead>'
        f"<tbody>{provider_rows}</tbody></table>"
    )

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AlphaFund-Daily 系統健康</title>
<style>{_HEALTH_CSS}</style>
</head>
<body>
{nav_html}
<div class="wrap">
<header>
<h1>🩺 系統健康</h1>
<div class="meta">彙整每日資料管道執行狀態與 LLM 供應商使用 ｜ 頁面生成：{_esc(now)}（Asia/Taipei）</div>
</header>
<div class="stat-row">{stats}</div>

<h2>每日執行狀態</h2>
<div class="scroll">{daily_table}</div>

<h2>LLM 供應商使用彙總</h2>
{provider_table}

<h2>說明</h2>
<div class="scroll" style="padding:12px;background:var(--card);border:1px solid var(--line);border-radius:8px;font-size:13px">
<ul style="margin:0;padding-left:18px">
<li><b>深度分析</b>＝當日完成 LLM 深度分析之檔數（目標 25）。</li>
<li><b>跳過</b>＝供應商鏈全數額度用罄（429）而未分析；<b>錯誤</b>＝個別分析失敗。</li>
<li><b>供應商分布</b>＝該日深度分析實際使用的 LLM 供應商與次數（供應商鏈自動切換）。</li>
<li>資料來源：data/history/ 下之 analysis.json.gz 與 snapshot.json.gz。</li>
</ul>
</div>

<footer>
<p>本頁由每日自動化管線生成，反映每日 06:00 排程之執行結果。</p>
</footer>
</div>
</body>
</html>"""


def generate_health(docs_dir: Path | None = None) -> Path:
    """生成 docs/health.html。"""
    from .report import _navbar_html
    from .pipeline import latest_date

    entries = build_health_data()
    if not entries:
        raise FileNotFoundError("data/history 下無健康資料")
    docs_dir = docs_dir or PROJECT_ROOT / "docs"
    nav = _navbar_html(is_latest=True, date=latest_date(), active="health")
    html = render_health_page(entries, nav)
    path = docs_dir / "health.html"
    path.write_text(html, encoding="utf-8")
    return path
