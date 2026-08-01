# 歷史報告日曆瀏覽（Calendar Archive）

日期：2026-08-01｜狀態：已完成

## 1. 目標

首頁 `docs/index.html` 預設顯示**最新報告**，並提供**日曆界面**點選歷史日期查看該日報告。每日排程自動累積歷史。

## 2. 檔案結構

```
docs/
├── index.html                 首頁＝最新完整報告 + 日曆（預設最新）
└── archive/
    └── <YYYY-MM-DD>.html      每日歷史報告頁（精簡版 + 日曆 + 回最新）
```

## 3. 設計（report.py）

| 元件 | 說明 |
| :--- | :--- |
| `render_report(..., compact, calendar_html, top_links)` | 報告頁；`compact=True` 僅前 50 名排名表（歷史頁），`False` 為完整 2128 列（首頁） |
| `render_calendar(dates, current, base)` | 月曆 widget：內嵌可用日期 JSON + 小段 vanilla JS；有報告日期→連結，無→灰字；上/下月切換；`base` 依頁面位置（`archive/` 或同目錄 `""`） |
| `render_archive_page` / `generate_archive` | 遍歷 `data/history/*` 重產全部 archive 頁 + 首頁 |

- 各頁內嵌完整可用日期清單，月曆獨立可瀏覽。
- 檔案相對路徑，相容 GitHub Pages 子路徑部署。

## 4. 生成與維護

- CLI：`uv run alphafund archive`（重產全部）／`daily`（管線結束自動 archive）。
- Workflow：`daily` 已含 archive 生成 → commit `data/` + `docs/`，歷史自動累積。

## 5. 驗證

- 單元測試：48 項通過（月曆日期標記、compact 排名上限、calendar/top_links 注入、HTML escape）。
- 瀏覽器驗證（2026-08-01）：
  - index：完整排名 2,128 列、月曆標記 8/1 可點、月曆連結 `archive/2026-08-01.html`。
  - 點 8/1 → archive 頁：精簡 50 列、21 個案卡片、月曆同目錄連結、回最新 `../index.html`。
  - 月曆 8月↔9月切換正常。
- Archive 頁體積 ~53KB（vs 首頁 654KB），控制 repo 成長。

## 6. 後續（另開輪次）

- 評分／排名隨時間的趨勢比較圖 → 已於 M5（見 `m5-trend-comparison.md`）完成。
- 多日報告並排比較 → 已於 M5 完成。
