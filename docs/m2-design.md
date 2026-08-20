# M2 設計文件 — AI 分析模組

日期：2026-08-01｜狀態：已完成（含 Gemini 實跑驗證）

## 1. 目標與範圍

M2 在 M1 資料之上加入分析層，產出「每日分析結果」作為 M3 報告的輸入：

1. **規則初評分**（全體 Fund Universe）→ 完整排名（ADR-0003）。
2. **前段基金 LLM 深度分析**（預設前 10 名）→ 新聞摘要、情緒、價值評分（40/40/20）、購入模式、優劣勢、綜合評級。
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

## 3. 規則初評分（scoring.py，ADR-0012 穩定導向）

| 維度 | 配分 | 公式 |
| :--- | :--- | :--- |
| 成長品質 | 0–35 | `35 × (1 − e^(−長期報酬% / 40))`；長期報酬 = 6M×0.15 + 1Y×0.30 + 2Y×0.25 + 3Y×0.30（不含 1M/3M，報酬遞減） |
| 穩定持續 | 0–35 | 長期正報酬(1Y/2Y/3Y 各+5) + 無深回撤(最差期分層) + 近期未急跌(1M/3M) |
| 收入加分 | 0–15 | `max(min(15, 有效配息率×2.0), 四級保底)`；有效配息率 = 名目配息率 × 收益品質；保底：完整7/無資料5/折半4/真本金3 |
| DCA 加分 | 0–10 | `clamp(DCA年報酬%×0.4, 0, 10) × 穩定持續分/35`；每月$100×12月模擬（1M/3M/6M/1Y 錨點內插推估，含配息現金） |
| 新聞聲量 | 0–5 | `min(5, 近7日基金特定相關新聞數 × 1)`（5 則封頂） |
| 風險調整 | −8~+3 | RR1 +3 / RR2 +1.5 / RR3 0 / RR4 −4 / RR5 −8（TDCC query-details） |
| 槓桿懲罰 | −15 | 名稱含 槓桿｜放空｜反向｜Inverse｜Leveraged｜Daily Nx（貨幣避險「對沖/Hedged」不算） |

- 排序：初評分 ↓ → 長期報酬% ↓ → 名稱 ↑（確定性、可重現）。
- 初評分僅用於篩選前段基金與提供完整排名；**前段之最終分數以 LLM 深度分析為準**。
- 配息資料源：TDCC `info-dividend/query`（`fetch_dividends`）；風險等級源：TDCC `fund-basic/query-details`（`fetch_fund_details`）。

## 4. LLM 深度分析（llm.py / analyzer.py）

- 供應商鏈（ADR-0007）：`LLM_PROVIDER_CHAIN` 依序嘗試，429 自動切換下一家。
  - **openrouter**：`google/gemma-4-26b-a4b-it:free`（免費，50 次/日/模型）。
  - **gemini**：`gemini-3.6-flash` Free Tier（RPD≈17/日）。
  - **groq**：`llama-3.3-70b-versatile`（免費，~14,400 次/日）。
- temperature 0.2。
- 端點：`{GEMINI_API_URL}/{model}:generateContent?key={KEY}`，`responseMimeType=application/json`。
- **額度降級**：HTTP 429 → `QuotaExceeded` → 停止後續呼叫，未分析基金標記 `quota_skipped`，隔日自動恢復（RPD 每日太平洋午夜重置）。
- 瞬態錯誤以 tenacity 重試 3 次。
- Prompt（analyzer.py `SYSTEM_PROMPT`）依構想文件樣板：角色設定、評分矩陣（40% 總經產業 / 40% 績效風險 / 20% 情緒資金）、購入模式、優劣勢、綜合評級、Context-Bound 限制、JSON 輸出。
- 解析缺欄採安全預設（情緒→Neutral、分數→0、清單→空）。

## 5. 資料格式（data/history/<date>/analysis.json.gz）

```json
{
  "date": "2026-08-01",
  "top_n": 10,
  "deep_analyzed_count": 10,
  "funds": [
    {
      "fund_code": "LU...",
      "name": "...",
      "currency": "USD",
      "preliminary_score": 93.9,
      "preliminary_breakdown": {"growth_score": 30.0, "stability_score": 35.0, "income_bonus": 7.0, "news_score": 9.0, "risk_bonus": -4.0, "risk_level": "RR4", "effective_yield_pct": 3.5, "income_quality": 0.8, "long_term_return": 36.57, "news_count": 3.0},
      "rank": 1,
      "status": "deep_analyzed",
      "deep_analysis": {"news_summary": [...], "market_sentiment": "Positive", "value_score": 85, ...}
    }
  ]
}
```

## 6. 執行方式

```bash
# 預設使用 OpenRouter（gemma-4-26b:free）
OPENROUTER_API_KEY=... uv run alphafund m2                # 初評分 + 前 N 深度分析
OPENROUTER_API_KEY=... uv run alphafund m2 --top-n 3     # 僅前 3 檔（驗證用，省額度）
uv run alphafund m2 --no-llm                              # 僅初評分
# 改用 Gemini
LLM_PROVIDER=gemini GEMINI_API_KEY=... uv run alphafund daily --top-n 15
```

## 7. 驗證結果

- 單元測試：26 項通過（含初評分公式、prompt、JSON 解析、Gemini client 429/成功 mock）。
- 真實資料初評分（2026-08-01，2,128 檔）：前段涵蓋多家基金公司（生技/日本/亞洲成長/韓國科技），動能分數具鑑別度。
- **LLM 深度分析實跑（2026-08-01）**：前 16/25 檔成功，深度分數 75–86，評級皆「值得關注」（新聞匱乏下 LLM 趨於保守，1 檔 Positive）；第 17 檔觸發 429 → **降級機制生效**（剩餘 9 檔 `quota_skipped`）。期間標籤（1M/1Y/2Y）經 LLM 解讀與報酬數值交叉確認正確。
- 觀察：新聞訊號稀疏時，LLM 評級集中在「值得關注」，多樣性不足 — 屬 M4 評分校準範圍。

## 8. 已知限制與後續

- **新聞訊號弱**：M1 新聞以系列關鍵字抓取，初評分新聞權重僅 0–15；若需強化，M1 需改為基金特定新聞標記。
- **期間標籤**：navValue 期間對應為 TDCC 慣例假設，待以 `nav-profit/query-rate-of-return` 最終確認。
- **免費額度**：前 25 檔 × 1 次呼叫/日，遠低於免費額度；`quota_skipped` 機制確保額度用罄不中斷系統。
- **M3 前瞻**：`analysis.json.gz` 即為 M3 報告頁面的排名與個案解讀輸入。
