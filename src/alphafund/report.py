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

from .config import HISTORY_DIR, PROJECT_ROOT, TIMEZONE

REPORT_FILE = PROJECT_ROOT / "docs" / "index.html"

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
.wrap{max-width:980px;margin:0 auto;padding:24px 16px 48px}
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
@media (max-width:640px){.f-body .col{grid-template-columns:1fr}}
"""


def _esc(value: object) -> str:
    return html_mod.escape(str(value if value is not None else ""), quote=True)


def _load_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def load_report_data(date: str) -> tuple[dict, dict[str, dict]]:
    day = HISTORY_DIR / date
    analysis = _load_gz(day / "analysis.json.gz")
    nav = _load_gz(day / "nav.json.gz")
    return analysis, {n["fund_code"]: n for n in nav}


def _returns_html(fund_code: str, nav_by_code: dict[str, dict]) -> str:
    nav = nav_by_code.get(fund_code)
    if not nav:
        return "-"
    parts = []
    for label, key in _PERIODS:
        parts.append(f"{label} {_esc(nav.get("returns", {}).get(key, "-"))}%")
    return "　".join(parts)


def _detail_card(fa: dict, nav_by_code: dict[str, dict]) -> str:
    da = fa.get("deep_analysis") or {}
    name = fa["name"]
    rating = da.get("overall_rating") or "-"
    sentiment = da.get("market_sentiment") or "-"
    sent_cls = {"Positive": "sent-p", "Negative": "sent-n"}.get(sentiment, "sent-u")
    nav = nav_by_code.get(fa["fund_code"], {})
    score = da.get("value_score")
    score_txt = f"{score:.0f}" if score is not None else "-"

    return f"""<details id="fund-{_esc(fa['fund_code'])}">
<summary><span class="g">#{fa['rank']}</span>{_esc(name)}
　<span class="rating r-{_esc(rating)}">{_esc(rating)}</span>
　<span class="num">深度分數 {score_txt} · 初評分 {fa['preliminary_score']}</span></summary>
<div class="f-body">
<div class="col">
<div class="blk"><h4>淨值資訊</h4>淨值 {_esc(nav.get("nav", "-"))}（{_esc(nav.get("nav_date", "-"))}）<br>
期間報酬：{_returns_html(fa['fund_code'], nav_by_code)}<br>
通路：{_esc("、".join(fa.get("channels", [])) or "-")}</div>
<div class="blk"><h4>市場情緒</h4><span class="{sent_cls}">{_esc(sentiment)}</span>
<h4>購入模式</h4>{_esc(da.get("recommended_strategy", "-"))}<br>
{_esc(da.get("strategy_explanation", ""))}</div>
<div class="blk"><h4>新聞摘要</h4><ul>
{''.join(f"<li>{_esc(x)}</li>" for x in da.get("news_summary") or []) or '<li>無相關新聞</li>'}</ul>
<h4>評分理由</h4>{_esc(da.get("score_rationale", ""))}</div>
<div class="blk"><h4>優勢</h4><ul>{''.join(f"<li>{_esc(p)}</li>" for p in da.get("pros") or [])}</ul>
<h4>劣勢 / 風險</h4><ul>{''.join(f"<li>{_esc(c)}</li>" for c in da.get("cons") or [])}</ul></div>
</div>
<div class="tax">🏷️ 稅務標籤：境外所得（最低稅負制）｜免扣 2.11% 二代健保｜享 750 萬免稅額、100 萬免申報門檻</div>
</div></details>"""


def _ranking_rows(analysis: dict, nav_by_code: dict[str, dict]) -> str:
    rows = []
    for fa in analysis.get("funds", []):
        da = fa.get("deep_analysis") or {}
        rating = da.get("overall_rating") or ""
        deep = da.get("value_score")
        deep_txt = f"{deep:.0f}" if deep is not None else "—"
        sentiment = da.get("market_sentiment") or "—"
        sent_cls = {"Positive": "sent-p", "Negative": "sent-n"}.get(sentiment, "sent-u")
        rows.append(
            f"<tr><td class=\"num\">{fa['rank']}</td>"
            f"<td><a href=\"#fund-{_esc(fa['fund_code'])}\">{_esc(fa['name'])}</a></td>"
            f"<td class=\"num\">{fa['preliminary_score']}</td>"
            f"<td class=\"num\">{deep_txt}</td>"
            f"<td>{f'<span class=\"rating r-{_esc(rating)}\">{_esc(rating)}</span>' if rating else '—'}</td>"
            f"<td><span class=\"{sent_cls}\">{_esc(sentiment)}</span></td>"
            f"<td>{_esc(da.get('recommended_strategy') or '—')}</td></tr>"
        )
    return "".join(rows)


def render_report(analysis: dict, nav_by_code: dict[str, dict], date: str) -> str:
    now = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M")
    funds = analysis.get("funds", [])
    total = len(funds)
    deep_count = analysis.get("deep_analyzed_count", 0)
    scored = [f for f in funds if f.get("deep_analysis")]

    detail_cards = "".join(
        _detail_card(f, nav_by_code)
        for f in funds
        if f.get("deep_analysis")
    ) or "<p>（本日無深度分析資料）</p>"

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AlphaFund-Daily 每日報告｜{_esc(date)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
<h1>AlphaFund-Daily 每日境外基金投研報告</h1>
<div class="meta">報告日期：{_esc(date)} ｜ 頁面生成：{_esc(now)}（Asia/Taipei）</div>
</header>

<div class="stat-row">
<div class="stat"><b>{total}</b><span>目標基金（三通路 × USD）</span></div>
<div class="stat"><b>{deep_count}</b><span>深度分析檔數</span></div>
<div class="stat"><b>{len(scored)}</b><span>已產生 AI 評級</span></div>
</div>

<h2>基金排名</h2>
<p style="font-size:13px;color:var(--mut)">依 AI 初評分（動能 + 新聞聲量）排序；前段基金另有 LLM 深度分析。</p>
<details>
<summary><span class="g">▶</span> 展開／收合完整排名表（{total} 檔）</summary>
<div style="max-height:480px;overflow:auto;border-radius:8px">
<table>
<thead><tr><th>#</th><th>基金名稱</th><th class="num">初評分</th><th class="num">深度分數</th><th>評級</th><th>情緒</th><th>購入模式</th></tr></thead>
<tbody>{_ranking_rows(analysis, nav_by_code)}</tbody>
</table></div>
</details>

<h2>個案深度解讀（前 {deep_count} 名）</h2>
{detail_cards}

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
<p><b>免責聲明：</b>本報告由自動化程式與 AI 模型（Gemini API）生成，僅供學術研究與個人資產管理參考，不構成任何投資招攬、要約或決策依據。投資人應獨立判斷並審慎評估風險；過去績效不代表未來績效保證。</p>
<p>資料來源：TDCC 基金資訊觀測站（上架清單／淨值／績效）、Google News（新聞）。資料可能延遲或不完整。</p>
</footer>
</div>
</body>
</html>"""


def generate_report(date: str, out_file: Path | None = None) -> Path:
    analysis, nav_by_code = load_report_data(date)
    html_out = render_report(analysis, nav_by_code, date)
    path = out_file or REPORT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_out, encoding="utf-8")
    return path
