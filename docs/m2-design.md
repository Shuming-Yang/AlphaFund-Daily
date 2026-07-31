# M2 設計文件 — AI 分析模組

日期：2026-08-01｜狀態：已完成（LLM 實跑待 GEMINI_API_KEY）

## 1. 目標與範圍

M2 在 M1 資料之上加入分析層，產出「每日分析結果」作為 M3 報告的輸入：

1. **規則初評分**（全體 Fund Universe）→ 完整排名（ADR-0003）。
2. **前段基金 LLM 深度分析**（預設前 25 名）→ 新聞摘要、情緒、價值評分（40/40/20）、購入模式、優劣勢、綜合評級。
3. 合併為 `DailyAnalysis`，存於 `data/history/<日期>/analysis.json.gz`。

## 2. 架構

```
M1 快照 (universe+nav+news)
   │
   ├─ scoring.compute_analysis()  全體初評分 → 排序 → rank
   │
   └─ pipeline.run_m2()           取前 TOP_N_DEEP_ANALYSIS
        └─ llm.GeminiClient()     逐檔呼叫 Gemini（JSON mode）
             └─ analyzer.parse_deep_analysis() → DeepAnalysis
        （429 額度用罄 → 剩餘標 quota_skipped，優雅降級）
   │
   └─ save_analysis() → analysis.json.gz
```

## 3. 規則初評分（scoring.py）

| 維度 | 權重 | 公式 |
| :--- | :--- | :--- |
| 績效動能 | 0–85 | `30 + 動能% × 1.5`（動能 = navValue5..8 加權期間報酬 0.15/0.25/0.25/0.35） |
| 新聞聲量 | 0–15 | `min(15, 近7日相關新聞數 × 3)`（M1 新聞以系列關鍵字抓取，訊號弱） |

- 排序：初評分 ↓ → 動能% ↓ → 名稱 ↑（確定性、可重現）。
- 初評分僅用於篩選前段基金與提供完整排名；**前段之最終分數以 LLM 深度分析為準**。
- 期間對應採 TDCC 慣例（navValue5..10 = 1M/3M/6M/1Y/2Y/3Y），待以歷史淨值 API 最終確認。

## 4. Gemini 深度分析（llm.py / analyzer.py）

- 供應商：Gemini API Free Tier（ADR-0002），模型 `gemini-3.6-flash`（可經 `GEMINI_MODEL` 覆寫），temperature 0.2。
- 端點：`{GEMINI_API_URL}/{model}:generateContent?key={KEY}`，`responseMimeType=application/json`。
- **額度降級**：HTTP 429 → `QuotaExceeded` → 停止後續呼叫，未分析基金標記 `quota_skipped`，隔日自動恢復（RPD 每日太平洋午夜重置）。
- 瞬態錯誤以 tenacity 重試 3 次。
- Prompt（analyzer.py `SYSTEM_PROMPT`）依構想文件樣板：角色設定、評分矩陣（40% 總經產業 / 40% 績效風險 / 20% 情緒資金）、購入模式、優劣勢、綜合評級、Context-Bound 限制、JSON 輸出。
- 解析缺欄採安全預設（情緒→Neutral、分數→0、清單→空）。

## 5. 資料格式（data/history/<date>/analysis.json.gz）

```json
{
  "date": "2026-08-01",
  "top_n": 25,
  "deep_analyzed_count": 25,
  "funds": [
    {
      "fund_code": "LU...",
      "name": "...",
      "currency": "USD",
      "preliminary_score": 93.9,
      "preliminary_breakdown": {"momentum_score": 84.9, "news_score": 9.0, "momentum_pct": 36.57, "news_count": 3.0},
      "rank": 1,
      "status": "deep_analyzed",
      "deep_analysis": {"news_summary": [...], "market_sentiment": "Positive", "value_score": 85, ...}
    }
  ]
}
```

## 6. 執行方式

```bash
GEMINI_API_KEY=... uv run alphafund m2                # 初評分 + 前 25 深度分析
GEMINI_API_KEY=... uv run alphafund m2 --top-n 3     # 僅前 3 檔（驗證用，省額度）
uv run alphafund m2 --no-llm                          # 僅初評分
GEMINI_API_KEY=... uv run alphafund daily --top-n 25  # 完整 M1→M2
```

## 7. 驗證結果

- 單元測試：26 項通過（含初評分公式、prompt、JSON 解析、Gemini client 429/成功 mock）。
- 真實資料初評分（2026-08-01，2,128 檔）：前段涵蓋多家基金公司（生技/日本/亞洲成長/韓國科技），動能分數具鑑別度。
- LLM 深度分析實跑：待使用者提供 `GEMINI_API_KEY` 後驗證。

## 8. 已知限制與後續

- **新聞訊號弱**：M1 新聞以系列關鍵字抓取，初評分新聞權重僅 0–15；若需強化，M1 需改為基金特定新聞標記。
- **期間標籤**：navValue 期間對應為 TDCC 慣例假設，待以 `nav-profit/query-rate-of-return` 最終確認。
- **免費額度**：前 25 檔 × 1 次呼叫/日，遠低於免費額度；`quota_skipped` 機制確保額度用罄不中斷系統。
- **M3 前瞻**：`analysis.json.gz` 即為 M3 報告頁面的排名與個案解讀輸入。
