# M1 設計文件 — 資料管道

日期：2026-08-01｜狀態：已完成

## 1. 目標與範圍

M1 建立每日資料管道，產出三項原始資料集，作為 M2（AI 評分）與 M3（報告）的輸入：

1. **目標基金清單**（`data/universe.json`）— 三家通路（元大/匯豐/渣打）上架、計價幣別為 USD 的境外基金。
2. **每日淨值**（`data/history/<日期>/nav.json`）— 每檔基金最新淨值、淨值日期與期間報酬率。
3. **每日新聞**（`data/history/<日期>/news.json`）— 依基金關鍵字自 Google News RSS 取得之新聞池。

## 2. Spike 結論（關鍵發現）

M1 前置 spike 的結論，決定了整體實作方向：

| 發現 | 影響 |
| :--- | :--- |
| TDCC API 直接 POST 回 403，初判 reCAPTCHA 阻擋 | 一度考慮 Playwright / 轉向 MoneyDJ |
| 加上 **session cookie + 對應頁面 Referer** 後，純 HTTP 即 200 | 無需瀏覽器，CI 輕量（ADR-0005） |
| 三家通路在 TDCC「機構查詢」均有機構代碼 | 通路上架清單可全自動取得，無需爬通路官網 |
| TDCC 境外基金共 5,247 檔，**無任何新臺幣級別** | 幣別過濾改為僅 USD（ADR-0004） |
| 台媒自有 RSS 大多失效（工商 403、經濟日報/中央社無效） | 新聞以 Google News RSS 為主（Q2 之務實調整） |
| 通路基金數：元大 2,591｜匯豐 2,805｜渣打 2,603 | Universe = 通路 ∩ USD = **2,128 檔** |

## 3. 資料來源與 API

### 3.1 TDCC 基金資訊觀測站（唯一主源，ADR-0001）

基址：`https://www.fundclear.com.tw`。存取機制（ADR-0005）：

- 先 `GET /` 暖機取得 session cookie。
- POST 時帶 `Referer`（依端點對應頁面）。
- 純 `httpx`，`Content-Type: application/json`。

| API 端點 | 請求體 | 用途 |
| :--- | :--- | :--- |
| `POST /api/offshore/org-info/org-search/query-org-basic` | `{"orgType":"K"}` | 機構清單（K=證券商、N=銀行…） |
| `POST /api/offshore/org-info/org-search/query-org-detail` | `{"orgCode":"K9800"}` | 某機構上架基金（代碼+名稱） |
| `POST /api/offshore/fund-info/fund-search/query` | 篩選條件 + 分頁 | 境外基金記錄（幣別、淨值、報酬） |

### 3.2 三家通路機構代碼

| 通路 | 類型 | 機構代碼 |
| :--- | :--- | :--- |
| 元大證券 | 證券商（K） | `K9800` |
| 匯豐銀行 | 銀行（N） | `N0810` |
| 渣打銀行 | 銀行（N） | `N0520` |

### 3.3 新聞來源

- **Google News RSS**：`https://news.google.com/rss/search?q=<kw>&hl=zh-TW&gl=TW&ceid=TW:zh-Hant`，免費、無需 key、涵蓋鉅亨網等台媒。
- 查詢關鍵字取基金名稱「-」前之系列/主名稱並截短（去級別雜訊），同關鍵字去重。

## 4. 硬性過濾實作（filters.py）

| 過濾 | 實作 |
| :--- | :--- |
| 通路 | 基金代碼 ∈ 任一通路 `query-org-detail` 集合 |
| 幣別 | `currencyName` 對應 ISO ∈ `config.ALLOWED_CURRENCIES`（僅 USD） |
| 收入屬性 | 資料源即 TDCC「境外」區，天然排除境內基金（ISIN 非 TW 開頭） |

## 5. 模組架構

```
src/alphafund/
├── config.py       通路/幣別/API/路徑 常數
├── models.py       Fund、NewsItem、DailySnapshot（pydantic）
├── filters.py      currency_to_iso、filter_funds
├── tdcc.py         TdccClient（cookie session + Referer + tenacity retry + 分頁）
├── news.py         Google News RSS 抓取、關鍵字、去重
├── pipeline.py     build_universe、save_snapshot、run_m1
└── cli.py          alphafund CLI（m1 / universe）
scripts/run_m1.py   執行入口
tests/              單元測試（MockTransport，不觸網）
```

## 6. 資料格式

- `data/universe.json`：最新清單（本機工作檔，gitignore；歷史留存以下方 gz 檔為主）。
- `data/history/<YYYY-MM-DD>/`（歷史檔以 `.json.gz` 儲存，單日約 0.3MB，一年約 0.12GB，利於 git 長期留存）：
  - `snapshot.json.gz`：完整快照（DailySnapshot）
  - `universe.json.gz`：當日 `Fund[]`
  - `nav.json.gz`：當日淨值（fund_code / nav / nav_date / returns / channels）
  - `news.json.gz`：當日 `NewsItem[]`

## 7. 執行方式

```bash
uv run alphafund m1                       # 完整管線（universe+nav+news+快照）
uv run alphafund m1 --news-limit 50      # 限制新聞抓取基金數
uv run alphafund m1 --no-save            # 不寫檔
uv run alphafund universe                 # 僅重建 universe.json
uv run pytest                             # 單元測試
```

## 8. 驗證結果（2026-08-01）

- TDCC 境外基金記錄：5,247 → **Universe（通路 ∩ USD）：2,128 檔**。
- 含最新淨值：2,051 檔（96.4%）；樣本淨值日期 2026/07/30（最新交易日）。
- 新聞：限 30 檔抓取得 21 筆（同系列關鍵字去重）。
- 單元測試：12 項通過。

## 9. 已知限制與後續

- **新聞關鍵字品質**：以「-」前系列名查詢，系列內多級別共用同一關鍵字；M2 依前段基金深度分析時可改用精確級別名或系列+主題詞。
- **TDCC 防護變動風險**：若 TDCC 未來啟用嚴格 reCAPTCHA 驗證或封鎖 Referer 直連，需退回 Playwright 方案（ADR-0005）。
- **資料變動**：通路在架清單、淨值欄位可能隨 TDCC 改版異動，需定期以測試與 CI 驗證守護。
- **M2 前瞻**：新聞情緒分類與評分將以本管道之 `nav.json`（含期間報酬）與 `news.json` 為輸入。
