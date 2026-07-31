# M3 設計文件 — 報告頁面與每日排程

日期：2026-08-01｜狀態：已完成

## 1. 目標與範圍

M3 將 M2 分析結果落地為可閱讀之每日報告，並以 GitHub Actions 每日自動化：

1. **HTML5 單頁報告**（`docs/index.html`）：排名表 + 前段基金可折疊個案（Q7 定案）。
2. **GitHub Actions 每日 06:00 排程**（`.github/workflows/daily_report.yml`）：M1 → M2 → 報告 → commit 回 repo。
3. **GitHub Pages 發布**：私有 repo（Pro），以 `docs/` 目錄發布（Q6 定案）。

## 2. 報告頁面（report.py）

單頁自含 HTML5，繁體中文，無外部依賴（inline CSS）：

| 區塊 | 內容 |
| :--- | :--- |
| 頁首 | 報告日期、頁面生成時間（Asia/Taipei）、統計（基金數 / 深度分析數 / 評級數） |
| 排名表 | 全體 2,128 檔，置於 `<details>` 內可收合；依初評分排序，含初評分/深度分數/評級/情緒/購入模式 |
| 個案解讀 | 前段（有深度分析者）各一 `<details>` 折疊卡片：淨值與期間報酬、新聞摘要、評分理由、購入模式、優劣勢、稅務標籤 |
| 稅務說明 | 境外所得、100 萬免申報、750 萬免稅額、免二代健保 |
| 頁尾 | 免責聲明 + 資料來源（TDCC / Google News） |

- 讀取 `analysis.json.gz` + `nav.json.gz`（依 `fund_code` 合併）。
- 所有輸出經 HTML escape，防 XSS。
- 生成：`uv run alphafund report --date YYYY-MM-DD`（`daily` 指令自動執行）。

## 3. 每日排程（daily_report.yml）

- **排程**：`cron: '0 22 * * *'`（UTC）= 每日 AM 06:00 台灣時間。
- **流程**：checkout → `astral-sh/setup-uv` + `uv sync --frozen` → `alphafund daily --top-n 25 --news-limit 200`（`GEMINI_API_KEY` 由 repo secret 傳入）→ commit `data/` + `docs/` → push。
- **權限**：`permissions: contents: write`（需 repo Settings → Actions → General → Workflow permissions = Read and write）。
- **並發**：`concurrency` 群組避免同日重疊執行；`timeout-minutes: 120`。
- **Key**：secret 未設定時 `GeminiClient` 會明確報錯；本機驗證可 `--no-llm`。

## 4. 新聞目標調整（M1 改良）

`run_m1` 的 `news_limit` 改為「**動能排序前 N 檔**」作為新聞抓取目標（原先為清單前 N 檔），確保兩階段（ADR-0003）前段基金有新，涵蓋深度分析對象。工作流以 `--news-limit 200` 控制成本與 Google 負載。

## 5. 發布設定（需帳號 owner 於網頁操作）

1. **Workflow 權限**：Settings → Actions → General → Workflow permissions → 勾選 **Read and write permissions**。
2. **GitHub Pages**：Settings → Pages → Source 選 **Deploy from a branch** → branch **master** → 目錄 **/docs**。
3. **Secret 確認**：Settings → Secrets and variables → Actions → `GEMINI_API_KEY` 已存在。

## 6. 驗證結果

- 單元測試：29 項通過（新增 report 生成、HTML escape、排名表/卡片結構）。
- `docs/index.html`（2026-08-01）：2,128 排名列、16 個案卡片、錨點跳轉、`<details>` 展開正常（瀏覽器 DOM 驗證）。
- 手動觸發：`gh workflow run daily_report.yml` 或網頁 Actions → Run workflow。

## 7. 已知限制與後續

- **報告體積**：`index.html` 約 650KB，每日 commit → 一年約 0.24GB；若過大可改為僅前段個案頁 + 完整排名分頁。
- **Pages 建置延遲**：私有 repo Pages 發布可能需數分鐘；免費帳號不支援私有 Pages（本專案為 Pro）。
- **M4 前瞻**：評分多樣性校準、新聞品質、429 恢復策略（額度耗盡時隔日補分析）。
