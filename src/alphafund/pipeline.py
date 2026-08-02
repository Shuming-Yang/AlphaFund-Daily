"""M1/M2 資料管道編排：清單/淨值/新聞 → 初評分排名 → LLM 深度分析。"""
from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import CHANNELS, DIVIDEND_MONTHS, HISTORY_DIR, TIMEZONE, TOP_N_DEEP_ANALYSIS, UNIVERSE_FILE
from .analyzer import SYSTEM_PROMPT, build_user_prompt, parse_deep_analysis
from .filters import filter_funds
from .llm import LLMClient, QuotaExceeded, get_llm_client
from .models import DailyAnalysis, DailySnapshot, DividendRecord, Fund, FundAnalysis, NewsItem
from .news import fund_matches_series, fund_matches_title, fetch_universe_news
from .scoring import income_class_from_name, preliminary_score, strategy_from_signals
from .tdcc import TdccClient

logger = logging.getLogger(__name__)


def today_str() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")


def latest_date() -> str:
    """回傳 data/history/ 中最新日期（YYYY-MM-DD）。"""
    dates = [d.name for d in HISTORY_DIR.glob("????-??-??") if d.is_dir()]
    return max(dates) if dates else today_str()


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


def _dividend_window(months: int = DIVIDEND_MONTHS, ref: datetime | None = None) -> tuple[str, str]:
    """回傳配息基準日查詢區間（YYYY/MM, YYYY/MM）：近 months 個月至當月。"""
    now = ref or datetime.now(ZoneInfo(TIMEZONE))
    begin = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
    for _ in range(max(1, months - 1)):
        begin = (begin - timedelta(days=1)).replace(day=1)
    return begin.strftime("%Y/%m"), now.strftime("%Y/%m")


def _dividend_candidate(fund: Fund) -> bool:
    """是否需要抓取配息：配息型，或名稱含「收益」之「其他」基金。"""
    cls = income_class_from_name(fund.name)
    if cls == "配息型":
        return True
    if cls == "其他" and "收益" in fund.name:
        return True
    return False


def fetch_dividends(client: TdccClient, funds: list[Fund], months: int = DIVIDEND_MONTHS) -> int:
    """為配息候選基金抓取近 N 月配息紀錄並寫入 Fund.dividends。

    回傳有配息紀錄之基金數；累積型基金與查無資料者略過。
    """
    begin, end = _dividend_window(months)
    targets = [f for f in funds if _dividend_candidate(f)]
    logger.info("配息候選基金: %d（區間 %s ~ %s）", len(targets), begin, end)
    with_data = 0
    for idx, fund in enumerate(targets, start=1):
        try:
            rows = client.query_dividend(fund.fund_code, begin, end)
        except Exception as exc:  # noqa: BLE001 — 單檔失敗不中斷管道
            logger.warning("配息查詢失敗 %s (%s): %s", fund.name[:24], fund.fund_code, exc)
            continue
        if rows:
            fund.dividends = [DividendRecord.from_tdcc(r) for r in rows]
            with_data += 1
        if idx % 100 == 0:
            logger.info("配息進度: %d/%d（%d 檔有配息）", idx, len(targets), with_data)
    logger.info("配息抓取完成: %d/%d 檔有配息紀錄", with_data, len(targets))
    return with_data


def fetch_fund_details(client: TdccClient, funds: list[Fund]) -> int:
    """為全體基金抓取風險報酬等級（RR）/ 資產類別並寫入 Fund。"""
    with_rr = 0
    for idx, fund in enumerate(funds, start=1):
        try:
            d = client.query_fund_details(fund.fund_code)
        except Exception as exc:  # noqa: BLE001 — 單檔失敗不中斷管道
            logger.warning("基本資料查詢失敗 %s (%s): %s", fund.name[:24], fund.fund_code, exc)
            continue
        if not d:
            continue
        fund.risk_level = d.get("risk_level", "")
        fund.asset_class = d.get("asset_class", "")
        fund.invest_type = d.get("invest_type", "")
        if fund.risk_level:
            with_rr += 1
        if idx % 500 == 0:
            logger.info("基本資料進度: %d/%d（%d 檔有 RR）", idx, len(funds), with_rr)
    logger.info("基本資料抓取完成: %d/%d 檔有風險等級", with_rr, len(funds))
    return with_rr


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
    dividend: bool = True,
    details: bool = True,
) -> DailySnapshot:
    """執行完整 M1 管線並回傳快照。

    news_limit 指定時，新聞目標為「動能排序前 N 檔」而非清單前 N 檔，
    確保兩階段（ADR-0003）前段基金有新（涵蓋深度分析對象）。
    dividend 指定時，為配息候選基金抓取近 N 月配息紀錄（供配息率評分）。
    details 指定時，為全體基金抓取風險報酬等級（RR）/ 資產類別（供風險評分）。
    """
    date = date or today_str()
    funds: list[Fund] = []
    news: list[NewsItem] = []
    with TdccClient() as client:
        funds = build_universe(client)
        if dividend:
            fetch_dividends(client, funds)
        if details:
            fetch_fund_details(client, funds)
    if news_limit is None or news_limit > 0:
        targets = funds
        if news_limit is not None:
            from .scoring import momentum
            targets = sorted(
                funds,
                key=lambda f: -(momentum(f)[0] or 0.0),
            )[:news_limit]
            logger.info("新聞目標：動能前 %d 檔", len(targets))
        news = fetch_universe_news(targets)
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
    """與基金相關之新聞（WP3 分層）：優先基金特定匹配，無則退系列層。

    - 第一層：`fund_matches_title`（全名 / distinctive 標的在標題）— 精準。
    - 第二層：`fund_matches_series`（系列主名稱在標題）— 召回 fallback。
    """
    specific = [n for n in news if fund_matches_title(fund, n.title or "")]
    if specific:
        return specific[:limit]
    series = [n for n in news if fund_matches_series(fund, n.title or "")]
    return series[:limit]


def compute_analysis(
    funds: list[Fund],
    news: list[NewsItem],
    previous: DailyAnalysis | None = None,
) -> list[FundAnalysis]:
    """全體初評分 + 排名（ADR-0003）。

    傳入 previous（既有分析）時，依 fund_code 回填既有 deep_analysis，
    使重新評分（如 --no-llm）不遺失 LLM 深度分析結果。
    """
    prev_by_code: dict[str, FundAnalysis] = {}
    if previous is not None:
        prev_by_code = {f.fund_code: f for f in previous.funds}

    analyzed: list[FundAnalysis] = []
    for f in funds:
        score, breakdown = preliminary_score(f, news)
        fa = FundAnalysis(
            fund_code=f.fund_code,
            name=f.name,
            currency=f.currency,
            channels=f.channels,
            preliminary_score=score,
            preliminary_breakdown=breakdown,
            status="scored",
        )
        prev = prev_by_code.get(f.fund_code)
        if prev is not None and prev.deep_analysis is not None:
            fa.deep_analysis = prev.deep_analysis
            fa.provider = prev.provider
            fa.status = "deep_analyzed"
        analyzed.append(fa)
    # 確定性排序：初評分 ↓ → 長期報酬 ↓ → 名稱 ↑
    analyzed.sort(
        key=lambda a: (
            -a.preliminary_score,
            -a.preliminary_breakdown.get("long_term_return", 0.0),
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
    client: LLMClient,
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
            # 購入模式以規則覆寫（保證分化）；保留 LLM 原因
            rule_strategy = strategy_from_signals(fund)
            if rule_strategy != fa.deep_analysis.recommended_strategy:
                fa.deep_analysis.strategy_explanation = (
                    f"（依動能規則改判 {rule_strategy}）"
                    + (fa.deep_analysis.strategy_explanation or "")
                )
            fa.deep_analysis.recommended_strategy = rule_strategy
            fa.status = "deep_analyzed"
            fa.provider = getattr(client, "provider", "")
            logger.info("[%d/%d] %s → %s（%s）", idx + 1, len(top), fund.name[:30],
                        fa.deep_analysis.overall_rating, fa.provider or "-")
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

    # 載入既有分析（若有）以保留 deep_analysis（重新評分不遺失 LLM 結果）
    previous: DailyAnalysis | None = None
    prev_path = HISTORY_DIR / date / "analysis.json.gz"
    if prev_path.exists():
        try:
            with gzip.open(prev_path, "rt", encoding="utf-8") as fh:
                previous = DailyAnalysis.model_validate_json(fh.read())
        except Exception:  # noqa: BLE001 — 舊資料缺欄亦可載入
            logger.warning("既有分析載入失敗，將重新分析: %s", date)

    analyzed = compute_analysis(snapshot.funds, snapshot.news, previous=previous)
    top = analyzed[:top_n]
    logger.info("初評分完成，前 %d 名送深度分析", len(top))

    if llm and top:
        client = get_llm_client()
        try:
            deep_analyze(top, snapshot.funds, snapshot.news, date, client)
        finally:
            client.close()

    deep_analyzed = sum(1 for a in analyzed if a.deep_analysis is not None)

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
