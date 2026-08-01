# M6 報告體驗與品質（WP1–3 完成）

日期：2026-08-01｜狀態：進行中（WP1–3 完成，WP4 待做）

## 目標

改善報告瀏覽體驗與資料品質：
- WP1 首頁瘦身 + 銷售通路篩選（**已完成**）
- WP2 評分校準（item 3+4，**已完成**）
- WP3 新聞品質（item 5，**已完成**）
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

- **WP4 趨勢深化**：`value_score` 跨日序列；排名跳動高亮。

---

## WP3 — 新聞品質（已完成）

- `news.py`：雙查詢抓取（`fund_keyword`＝基金特定 distinctive＋`series_keyword`）、`is_low_signal` 低訊號過濾、`fund_matches_title`／`fund_matches_series` 匹配函式。
- `scoring.news_volume`：僅基金特定匹配（消除跨基金污染）。
- `pipeline.related_news`：分層（基金特定優先→系列 fallback）。
- 驗證（本機實抓，動能前 25 檔）：57 筆、0 低訊號殘留，含真實報導（工商時報「富坦生技領航基金獲獎」、鉅亨買基金「聯博國際科技」）。
- 決策詳見 ADR-0011；測試 90 項全綠（+7）。

---

## WP2 — 評分校準（已完成）

- `analyzer.py` SYSTEM_PROMPT 加「評分校準指引」（value_score 錨點：60 基準、常態 55–85、避免一律相近分數）與「評級決策指引」（強力推薦需 ≥2 維度轉佳、訊號不明預設中立觀望、評級與分數一致）。
- `parse_deep_analysis` 加**一致性覆寫**（ADR-0010）：評級合理帶（強力[75,100]／值得[55,89]／中立[40,74]／避開[0,54]），帶外覆寫為分數門檻評級並記錄；評級空缺由分數推導。
- `scoring.py` 檢視結論：初評分分布已健康（==100 僅 1 檔），**不需改動**。
- 測試 83 項全綠（新增 5 項：prompt 校準標記、帶內保留、帶外覆寫 ×2、空缺推導）。
- 驗證方式：排程驗證（下一個 06:00 執行後比對分布）。
