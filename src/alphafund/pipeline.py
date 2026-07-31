"""M1/M2 資料管道編排：清單/淨值/新聞 → 初評分排名 → LLM 深度分析。"""
from __future__ import annotations

import gzip
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import CHANNELS, HISTORY_DIR, TIMEZONE, TOP_N_DEEP_ANALYSIS, UNIVERSE_FILE
from .analyzer import SYSTEM_PROMPT, build_user_prompt, parse_deep_analysis
from .filters import filter_funds
from .llm import GeminiClient, QuotaExceeded
from .models import DailyAnalysis, DailySnapshot, Fund, FundAnalysis, NewsItem
from .news import fetch_universe_news
from .scoring import preliminary_score
from .tdcc import TdccClient

logger = logging.getLogger(__name__)


def today_str() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")


def build_universe(client: TdccClient) -> list[Fund]:
    """三通路上架基金 ∩ 允許幣別 → 目標基金清單。"""
    channel_sets: dict[str, set[str]] = {}
    for name, info in CHANNELS.items():
        rows = client.query_org_detail(info["org_code"])
        channel_sets[name] = {str(r["fundCode"]) for r in rows}
        logger.info("%s 上架基金: %d", name, len(channel_sets[name]))
    raw = client.query_all_funds(currency="all")
    logger.info("TDCC 境外基金記錄: %d", len(raw))
    funds = filter_funds(raw, channel_sets)
    logger.info("目標基金清單（通路 ∩ USD）: %d", len(funds))
    return funds


def _write_json_gz(path: Path, data) -> None:
    """以 gzip 壓縮寫入 JSON（歷史檔壓縮後單日約 0.3MB，利於 git 長期留存）。"""
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=2))


def save_snapshot(snapshot: DailySnapshot) -> Path:
    day_dir = HISTORY_DIR / snapshot.date
    day_dir.mkdir(parents=True, exist_ok=True)

    _write_json_gz(day_dir / "snapshot.json.gz", json.loads(snapshot.model_dump_json()))
    _write_json_gz(day_dir / "news.json.gz", [n.model_dump() for n in snapshot.news])
    nav = [
        {
            "fund_code": f.fund_code,
            "name": f.name,
            "currency": f.currency,
            "nav": f.nav,
            "nav_date": f.nav_date,
            "returns": f.returns,
            "channels": f.channels,
        }
        for f in snapshot.funds
    ]
    _write_json_gz(day_dir / "nav.json.gz", nav)
    _write_json_gz(day_dir / "universe.json.gz", [f.model_dump() for f in snapshot.funds])

    # 最新清單保留未壓縮，方便直接讀取
    UNIVERSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    UNIVERSE_FILE.write_text(
        json.dumps([f.model_dump() for f in snapshot.funds], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return day_dir


def run_m1(
    date: str | None = None,
    news_limit: int | None = None,
    save: bool = True,
) -> DailySnapshot:
    """執行完整 M1 管線並回傳快照。"""
    date = date or today_str()
    funds: list[Fund] = []
    news: list[NewsItem] = []
    with TdccClient() as client:
        funds = build_universe(client)
    if news_limit is None or news_limit > 0:
        news = fetch_universe_news(funds, limit=news_limit)
        logger.info("新聞項目: %d", len(news))
    else:
        logger.info("略過新聞抓取")

    snapshot = DailySnapshot(
        date=date, universe_count=len(funds), funds=funds, news=news
    )
    if save:
        path = save_snapshot(snapshot)
        logger.info("快照已寫入: %s", path)
    return snapshot


def _read_json_gz(path: Path) -> list:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def load_snapshot(date: str) -> DailySnapshot:
    """自 data/history/<date>/ 載入當日快照（funds + news）。"""
    day_dir = HISTORY_DIR / date
    if not (day_dir / "snapshot.json.gz").exists():
        raise FileNotFoundError(f"該日快照不存在: {day_dir}（請先執行 run_m1）")
    snap = DailySnapshot.model_validate_json(
        gzip.open(day_dir / "snapshot.json.gz", "rt", encoding="utf-8").read()
    )
    return snap


def related_news(fund: Fund, news: list[NewsItem], limit: int = 10) -> list[NewsItem]:
    """與基金相關之新聞：先比對完整級別名，再退而比對系列主名稱。"""
    names = [fund.name]
    if "-" in fund.name or "－" in fund.name:
        core = re.split(r"[－\-]", fund.name, maxsplit=1)[0].strip()
        if core:
            names.append(core)
    out = []
    for n in news:
        title = n.title or ""
        if any(name and name in title for name in names):
            out.append(n)
    return out[:limit]


def compute_analysis(
    funds: list[Fund], news: list[NewsItem]
) -> list[FundAnalysis]:
    """全體初評分 + 排名（ADR-0003）。"""
    analyzed: list[FundAnalysis] = []
    for f in funds:
        score, breakdown = preliminary_score(f, news)
        analyzed.append(
            FundAnalysis(
                fund_code=f.fund_code,
                name=f.name,
                currency=f.currency,
                channels=f.channels,
                preliminary_score=score,
                preliminary_breakdown=breakdown,
                status="scored",
            )
        )
    # 確定性排序：初評分 ↓ → 動能 ↓ → 名稱 ↑
    analyzed.sort(
        key=lambda a: (
            -a.preliminary_score,
            -a.preliminary_breakdown.get("momentum_pct", 0.0),
            a.name,
        )
    )
    for i, a in enumerate(analyzed, start=1):
        a.rank = i
    return analyzed


def deep_analyze(
    top: list[FundAnalysis],
    funds: list[Fund],
    news: list[NewsItem],
    date: str,
    client: GeminiClient,
) -> None:
    """對前段基金逐一送 LLM 深度分析；額度用罄即停止並標記其餘。"""
    fund_by_code = {f.fund_code: f for f in funds}
    for idx, fa in enumerate(top):
        fund = fund_by_code.get(fa.fund_code)
        if fund is None:
            fa.status = "error"
            continue

        user_prompt = build_user_prompt(fund, related_news(fund, news), date)
        try:
            raw = client.generate_json(SYSTEM_PROMPT, user_prompt)
            fa.deep_analysis = parse_deep_analysis(raw, fund.fund_code, date)
            fa.status = "deep_analyzed"
            logger.info("[%d/%d] %s → %s", idx + 1, len(top), fund.name[:30],
                        fa.deep_analysis.overall_rating)
        except QuotaExceeded:
            logger.warning("額度用罄，停止後續深度分析（尚餘 %d 檔）", len(top) - idx)
            for rest in top[idx:]:
                rest.status = "quota_skipped"
            break
        except Exception as exc:  # noqa: BLE001
            fa.status = "error"
            logger.error("深度分析失敗 %s: %s", fund.name[:30], exc)


def save_analysis(analysis: DailyAnalysis) -> Path:
    day_dir = HISTORY_DIR / analysis.date
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / "analysis.json.gz"
    _write_json_gz(path, json.loads(analysis.model_dump_json()))
    return path


def run_m2(
    date: str | None = None,
    top_n: int = TOP_N_DEEP_ANALYSIS,
    llm: bool = True,
    save: bool = True,
) -> DailyAnalysis:
    """執行 M2：初評分排名 → 前段 LLM 深度分析 → 合併分析結果。"""
    date = date or today_str()
    snapshot = load_snapshot(date)
    logger.info("載入 %s 快照: %d 檔基金, %d 筆新聞", date,
                len(snapshot.funds), len(snapshot.news))

    analyzed = compute_analysis(snapshot.funds, snapshot.news)
    top = analyzed[:top_n]
    logger.info("初評分完成，前 %d 名送深度分析", len(top))

    deep_analyzed = 0
    if llm and top:
        client = GeminiClient()
        try:
            deep_analyze(top, snapshot.funds, snapshot.news, date, client)
        finally:
            client.close()
        deep_analyzed = sum(1 for a in top if a.status == "deep_analyzed")

    analysis = DailyAnalysis(
        date=date, top_n=len(top), deep_analyzed_count=deep_analyzed, funds=analyzed
    )
    if save:
        path = save_analysis(analysis)
        logger.info("分析結果已寫入: %s", path)
    return analysis


def run_daily(
    date: str | None = None,
    news_limit: int | None = None,
    top_n: int = TOP_N_DEEP_ANALYSIS,
    llm: bool = True,
) -> tuple[DailySnapshot, DailyAnalysis]:
    """完整每日管線：M1 → M2。"""
    date = date or today_str()
    snapshot = run_m1(date=date, news_limit=news_limit)
    analysis = run_m2(date=date, top_n=top_n, llm=llm)
    return snapshot, analysis
