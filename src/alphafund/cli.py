"""alphafund CLI — M1 資料管道入口。"""
from __future__ import annotations

import argparse
import logging
import sys

from .pipeline import run_m1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alphafund",
        description="AlphaFund-Daily 資料管道（M1）",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="輸出詳細 log")
    sub = parser.add_subparsers(dest="cmd", required=True)

    m1 = sub.add_parser("m1", help="執行完整 M1 管線（清單+淨值+新聞+快照）")
    m1.add_argument("--date", help="快照日期 YYYY-MM-DD（預設今天）")
    m1.add_argument("--news-limit", type=int, default=None,
                    help="新聞抓取基金上限（0=不抓新聞；預設全體）")
    m1.add_argument("--no-save", action="store_true", help="不寫入 data/")

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
