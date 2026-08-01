# 趨勢比較（Trend Comparison）

日期：2026-08-01｜狀態：已完成

## 1. 目標

善用 `data/history/<date>/analysis.json.gz` 累積資料，於報告中加入**評分／排名／評級隨時間趨勢圖**與**多日並排比較**，協助觀察基金動能與排名變化。每日排程自動累積新資料點，歷史 ≥2 個交易日後趨勢自動浮現。

## 2. 資料來源與模型

- 每日 `analysis.json.gz` 內含全體 2,128 檔之 `preliminary_score`／`rank`，以及前段基金之 `deep_analysis.value_score`／`overall_rating` → 趨勢資料自第一天起即開始累積。
- 新增 `src/alphafund/trends.py`：`TrendPoint`（date／preliminary_score／rank／value_score／overall_rating／momentum_pct）、`build_time_series()`、`comparison_data()`、`trend_stats()`、`sparkline_svg()`。
- 渲染方式：**Server-side SVG**（ADR-0008），無 JS 依賴、輸出確定、可離線測試。

## 3. 功能範圍

| 元件 | 位置 | 內容 |
| :--- | :--- | :--- |
| 個案卡片「近期趨勢」 | `docs/index.html` 每張深度分析卡片 | 初評分＋排名雙 sparkline、區間統計、近 5 日迷你表 |
| 首頁「趨勢比較」 | `docs/index.html` | 前段基金 × 最近 14 個交易日並排表（每格＝排名，title 顯示當日初評分與評級）＋ 近窗變化 ＋ 排名 sparkline；可收合之初評分並排表 |
| 獨立趨勢頁 | `docs/trends.html` | 前段基金較大雙圖（初評分／排名）、區間統計、近 10 日迷你表；navbar「📈 趨勢」進入 |

- 歷史 <2 個交易日：顯示「歷史資料累積中」提示，版型不破壞。
- 精簡 archive 頁**不內嵌**趨勢圖（控制 repo 體積），但 navbar 仍提供趨勢頁連結。

## 4. 生成與維護

- CLI：`uv run alphafund trends`（單獨生成）；`uv run alphafund archive`／`daily` 於生成 archive 後一併更新 `trends.html`。
- Workflow：`daily` 指令已含 archive 生成 → 趨勢頁自動隨每日 06:00 更新，無需改動 `.github/workflows/`。

## 5. 驗證

- 單元測試：69 項通過（新增 `tests/test_trends.py` 12 項：時序建構、缺失日、SVG 形狀、排名倒序、<2 點邊界、比較視窗；`tests/test_report.py` 增 6 項：趨勢區塊注入、累積中提示、比較表、compact 排除趨勢、navbar 趨勢連結）。
- 瀏覽器驗證（temp 兩日資料）：
  - `trends.html`：25 檔基金各含初評分／排名雙圖＋迷你表＋區間統計，navbar 正確。
  - `index.html`：比較表 25 列 ×（基金＋2 日＋近窗變化＋排名趨勢），個案卡片含 sparkline（DOM 共 75 個 SVG）。
- 目前正式資料僅 1 日 → 正式 `docs/` 現顯示「累積中」，第二個交易日自動浮現。

## 6. 後續（另開輪次）

- 評級／價值分數（deep_analysis）跨日比較與趨勢。
- 趨勢頁加入基金搜尋／篩選（僅顯示某產業或動能區間）。
- 排名跳動告警（單日大幅上升/下降）。
