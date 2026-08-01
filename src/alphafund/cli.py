"""alphafund CLI — M1 資料管道入口。"""
from __future__ import annotations

import argparse
import logging
import sys

from .pipeline import run_daily, run_m1, run_m2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alphafund",
        description="AlphaFund-Daily 資料管道（M1/M2）",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="輸出詳細 log")
    sub = parser.add_subparsers(dest="cmd", required=True)

    m1 = sub.add_parser("m1", help="執行 M1（清單+淨值+新聞+快照）")
    m1.add_argument("--date", help="快照日期 YYYY-MM-DD（預設今天）")
    m1.add_argument("--news-limit", type=int, default=None,
                    help="新聞抓取基金上限（0=不抓新聞；預設全體）")
    m1.add_argument("--no-save", action="store_true", help="不寫入 data/")

    m2 = sub.add_parser("m2", help="執行 M2（初評分排名 + 前段 LLM 深度分析）")
    m2.add_argument("--date", help="分析日期 YYYY-MM-DD（預設今天；讀取當日快照）")
    m2.add_argument("--top-n", type=int, default=None, help="深度分析前 N 名（預設 25）")
    m2.add_argument("--no-llm", action="store_true", help="僅初評分，不呼叫 LLM")
    m2.add_argument("--no-save", action="store_true", help="不寫入檔案")

    daily = sub.add_parser("daily", help="完整每日管線（M1 → M2 → 報告）")
    daily.add_argument("--date", help="日期 YYYY-MM-DD（預設今天）")
    daily.add_argument("--news-limit", type=int, default=None)
    daily.add_argument("--top-n", type=int, default=None)
    daily.add_argument("--no-llm", action="store_true")

    report = sub.add_parser("report", help="由當日分析結果生成 HTML5 報告頁面 docs/index.html")
    report.add_argument("--date", help="報告日期 YYYY-MM-DD（預設最新快照日期）")
    report.add_argument("--out", default=None, help="輸出檔路徑（預設 docs/index.html）")

    archive = sub.add_parser("archive", help="重產全部歷史 archive 頁 + 首頁（最新報告 + 日曆）")

    uni = sub.add_parser("universe", help="僅重建目標基金清單並寫入 data/universe.json")
    uni.add_argument("--no-save", action="store_true", help="不寫入檔案")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.cmd == "m1":
            snap = run_m1(date=args.date, news_limit=args.news_limit, save=not args.no_save)
            print(f"快照 {snap.date}: 基金 {snap.universe_count} 檔, 新聞 {len(snap.news)} 筆")
        elif args.cmd == "m2":
            analysis = run_m2(
                date=args.date,
                top_n=args.top_n or 25,
                llm=not args.no_llm,
                save=not args.no_save,
            )
            print(f"分析 {analysis.date}: 初評分 {len(analysis.funds)} 檔, "
                  f"深度分析 {analysis.deep_analyzed_count} 檔")
        elif args.cmd == "daily":
            snap, analysis = run_daily(
                date=args.date,
                news_limit=args.news_limit,
                top_n=args.top_n or 25,
                llm=not args.no_llm,
            )
            from .report import generate_archive
            index, pages = generate_archive()
            print(f"每日 {snap.date}: 基金 {snap.universe_count} 檔, 新聞 {len(snap.news)} 筆, "
                  f"深度分析 {analysis.deep_analyzed_count} 檔, 首頁 {index}（archive {len(pages)} 頁）")
        elif args.cmd == "archive":
            from .report import generate_archive
            index, pages = generate_archive()
            print(f"archive 已生成: 首頁 {index} + {len(pages)} 頁歷史報告")
        elif args.cmd == "report":
            from pathlib import Path
            from .pipeline import latest_date
            from .report import generate_report
            date = args.date or latest_date()
            out = generate_report(date, Path(args.out) if args.out else None)
            print(f"報告已生成: {out}")
        elif args.cmd == "universe":
            from .pipeline import build_universe
            from .tdcc import TdccClient
            with TdccClient() as client:
                funds = build_universe(client)
            if not args.no_save:
                from .pipeline import UNIVERSE_FILE
                import json
                UNIVERSE_FILE.parent.mkdir(parents=True, exist_ok=True)
                UNIVERSE_FILE.write_text(
                    json.dumps([f.model_dump() for f in funds], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"universe.json 已寫入: {UNIVERSE_FILE}（{len(funds)} 檔）")
            else:
                print(f"目標基金清單: {len(funds)} 檔")
        else:
            raise SystemExit(f"未知指令: {args.cmd}")
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
