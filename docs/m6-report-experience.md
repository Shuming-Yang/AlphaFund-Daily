# M6 報告體驗與品質（WP1 完成）

日期：2026-08-01｜狀態：進行中（WP1 完成，WP2–4 待做）

## 目標

改善報告瀏覽體驗與資料品質：
- WP1 首頁瘦身 + 銷售通路篩選（**已完成**）
- WP2 評分校準（item 3+4）
- WP3 新聞品質（item 5）
- WP4 趨勢深化（item 6+7）

---

## WP1 — 首頁瘦身 + 通路 filter（已完成）

### Item 8：index 體積 669KB → 150KB

- 首頁排名表精簡為**前 300 列**（`INDEX_RANK_LIMIT`）。
- 完整排名拆分至獨立頁 **`docs/ranking.html`**（最新全體 2,128 列，僅覆寫一份）。
- 歷史 archive 頁維持精簡（前 50 列）。
- navbar 新增「🏆 完整排名」；排名區提供 `ranking.html` 連結。
- CLI：`alphafund ranking` 單獨生成；`archive`／`daily` 自動一併更新。

### Item 2b：銷售通路 filter

- 排名表 `<tr>` 與個案卡片 `<details>` 標 `data-ch`（如 `data-ch="元大證券,匯豐銀行"`）。
- 排名區上方 filter chips：`[全部] [元大證券] [匯豐銀行] [渣打銀行]`，顯示各自列數。
- Vanilla JS 同步篩選排名表＋個案卡片（比照月曆做法）。
- 套用頁面：`index.html`（前 300）＋ `ranking.html`（全體）；**archive 頁不套用**。
- 決策詳見 ADR-0009。

## 驗證（WP1）

- 單元測試 78 項全綠（新增 9 項：rank_limit 標籤、data-ch、filter 計數與上限、注入、compact 排除）。
- 瀏覽器驗證（Playwright）：
  - `ranking.html`：2,128 列；點「渣打銀行」→ 1,578 列（與資料一致）；「全部」還原。
  - `index.html`：300 列；點「元大證券」→ 排名與卡片同步篩選。
  - archive 頁無 filter、無 active 高亮、ranking/trends 連結正常。
- 檔案大小：index 148KB、ranking 708KB（單份）、archive 66.9KB、trends 6.8KB。

---

## WP2–4（待做）

- **WP2 評分校準**：`analyzer.py` prompt 加分布準則（value_score 常態 55–85、評級預設中立觀望）；修正「模型→評級」系統性偏誤；`scoring.py` 檢視 100 頂格。
- **WP3 新聞品質**：基金特定標記、來源白名單、去重。
- **WP4 趨勢深化**：`value_score` 跨日序列；排名跳動高亮。
