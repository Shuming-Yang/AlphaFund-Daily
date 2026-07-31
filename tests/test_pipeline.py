"""快照寫入測試。"""
from __future__ import annotations

import gzip
import json

import alphafund.pipeline as pipeline
from alphafund.models import DailySnapshot, Fund


def _snapshot() -> DailySnapshot:
    return DailySnapshot(
        date="2026-08-01",
        universe_count=1,
        funds=[
            Fund(
                fund_code="0352",
                name="測試基金",
                currency="USD",
                nav="1.500000",
                nav_date="2026/07/30",
            )
        ],
    )


def test_save_snapshot_writes_gzipped_history(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "HISTORY_DIR", tmp_path / "history")
    monkeypatch.setattr(pipeline, "UNIVERSE_FILE", tmp_path / "universe.json")

    day = pipeline.save_snapshot(_snapshot())

    assert (day / "snapshot.json.gz").exists()
    assert (day / "nav.json.gz").exists()
    assert (day / "news.json.gz").exists()
    assert (day / "universe.json.gz").exists()

    with gzip.open(day / "nav.json.gz", "rt", encoding="utf-8") as fh:
        nav = json.load(fh)
    assert nav[0]["fund_code"] == "0352"
    assert nav[0]["nav"] == "1.500000"

    # 最新清單為未壓縮，可直接讀取
    latest = json.loads((tmp_path / "universe.json").read_text(encoding="utf-8"))
    assert latest[0]["name"] == "測試基金"
