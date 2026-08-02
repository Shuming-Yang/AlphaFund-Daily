[繁體中文](./README.md) · [**English**](./README.en.md)

---

# AlphaFund-Daily — Daily AI Offshore Fund Research & Selection Report

![Daily Report](https://github.com/Shuming-Yang/AlphaFund-Daily/actions/workflows/daily_report.yml/badge.svg)
![Last Commit](https://img.shields.io/github/last-commit/Shuming-Yang/AlphaFund-Daily)
![License](https://img.shields.io/badge/license-MIT-blue)
![Repo Size](https://img.shields.io/github/repo-size/Shuming-Yang/AlphaFund-Daily)
![Top Language](https://img.shields.io/github/languages/top/Shuming-Yang/AlphaFund-Daily)

An automated daily investment research and selection system for offshore mutual funds. Every morning the project automatically scans the offshore funds offered by designated financial channels, aggregates global financial news for filtering, and uses AI models to perform value scoring, buying-pattern analysis, and pros-and-cons evaluation — producing a structured daily report page that helps investors quickly grasp opportunities and tax benefits.

This document is the full specification for the project, covering target universe, filtering mechanisms, daily workflow, scoring framework, tax notes, and development roadmap. Detailed implementation will be planned step by step using the "grill-with-docs" skill.

---

## Overview

With thousands of offshore funds and countless share classes worldwide, it is hard for individual investors to track NAV movements, financial news, and tax implications every day. AlphaFund-Daily automates this process:

- Fetches daily fund NAV and performance data automatically — no manual queries.
- Searches for financial news relevant to each target over the past 24 hours and filters out noise.
- Runs quantitative scoring and qualitative analysis through an AI model, producing consistent, comparable daily reports.
- Keeps every screening and recommendation focused on instruments investors can actually buy, with tax advantages.

## Core Goals & Design Principles

| Principle | Description |
| :--- | :--- |
| Automation | Runs on a daily schedule with no manual intervention, producing the freshest report each morning. |
| Precise Filtering | No blind market-wide scraping — three hard filters lock onto actionable targets. |
| Tax-Oriented | Targets genuine offshore funds to highlight tax advantages under Taiwan's AMT regime. |
| Actionable | Analysis results can be executed directly in the investor's existing brokerage or bank accounts. |
| Compliance | All analysis is for research reference only, with a built-in disclaimer — not investment advice. |

## Target Universe & Hard Filters

The project narrows thousands of offshore funds down to an actionable, trackable, tax-efficient target list through a three-layer filtering mechanism.

### Distribution Channels

Only funds offered through the following three channels:

| Channel | Role |
| :--- | :--- |
| Yuanta Securities (元大證券) | Both cross-border (複委託) and fund distribution channel |
| HSBC (匯豐銀行) | Foreign bank; focuses on products from global fund houses |
| Standard Chartered (渣打銀行) | Foreign bank; focuses on products from global fund houses |

This constraint guarantees every fund in the report can be purchased directly from the investor's existing brokerage or bank accounts.

### Settlement Currencies

Only USD share classes are kept.

TDCC offshore-fund data contains no TWD (New Taiwan Dollar) share classes (see ADR-0004), so the currency filter covers USD only. Other currencies (ZAR, AUD, EUR, CNY, JPY, etc.) are excluded to reduce exchange-rate noise and focus on the mainstream reserve/settlement currency.

### Tax Category (100% Offshore Income)

Only "genuine offshore funds" domiciled outside Taiwan:

- ISIN Code must NOT start with "TW" (e.g. LU Luxembourg, IE Ireland, KY Cayman).
- Domicile must not be Taiwan.
- Funds issued by domestic Taiwanese investment trusts are excluded.

For funds meeting the above conditions, both trading gains (capital gains) and distributions are classified as "offshore income", governed by Taiwan's Income Basic Tax Act (Alternative Minimum Tax).

### Exclusion Summary

| Condition | Excluded |
| :--- | :--- |
| Channel | Funds not sold via the three designated channels |
| Currency | Share classes other than USD |
| Domicile | Taiwan-domiciled funds, TW-prefixed ISIN |
| Income Type | Targets that are not 100% offshore income |

## Daily Workflow (AM 06:00)

Every day at 06:00 the following four stages run automatically to produce the day's report.

### Stage 1: Data Collection

- Fetch the latest daily NAV and recent performance for target funds from public sources.
- Compare against the existing target list to update listing status and channel information.
- Apply hard filters to confirm currency, domicile, and channel compliance.

### Stage 2: News Collection & Filtering

- Retrieve financial news relevant to the analyzed funds over the past 24 hours.
- Remove duplicates and unrelated coverage; keep only information tied to the fund's assets, sectors, or regions.
- Pre-tag news sentiment as input for downstream scoring.

### Stage 3: AI Analysis

- Summarize key news points and classify market sentiment (Positive / Neutral / Negative).
- Compute an "AI Value Score" (0–100) using the scoring matrix, with reasons.
- Recommend a buying pattern based on volatility and trend.
- Produce objective pros-and-cons analysis and tax-allocation hints.

### Stage 4: Ranking & Report Generation

- Aggregate all analysis into a ranking list and per-fund deep dives.
- Convert to an easy-to-read daily static web report.
- Update the report homepage with the ranking table, strengths/weaknesses, and buying-pattern recommendations.

## Scoring Matrix & Analysis Metrics

The daily overall rating uses a multi-dimensional weighted design:

| Dimension | Weight | What is evaluated |
| :--- | :---: | :--- |
| Macro & Sector Sentiment | 40% | News attention over 24h, central-bank policy, sector tailwinds |
| Performance & Risk | 40% | Recent NAV trend, relative performance vs category, drawdown stability |
| Market Sentiment & Flows | 20% | Media/institutional coverage volume and sentiment |

### Overall Rating Bands

| Rating | Meaning |
| :--- | :--- |
| Strong Buy | Multiple indicators improving together, clear trend |
| Watch | Promising but with factors still to confirm |
| Neutral | Mixed signals, stay observant |
| Avoid | Clear negative signals, elevated risk |

### Buying-Pattern Recommendations

| Pattern | When it fits |
| :--- | :--- |
| Dollar-Cost Averaging (DCA) | High volatility but favorable long-term trend |
| Tranched Lump-Sum | Base-building complete, clear trend, volatility converging |
| Hold / Wait | Signals unclear or negative risks unresolved |

## Preliminary Score — Calculation Rules

The daily ranking is based on the **preliminary score**, computed by deterministic rules over the entire universe (`scoring.py`). The design is **stability-first** — stable profit beats high profit, sustained profit beats short-term spikes, steady growth beats high volatility (see [ADR-0012](./docs/adr/0012-stable-risk-adjusted-scoring.md)).

```
Preliminary Score = Growth Quality(0–35) + Stability(0–35) + Income(0–15) + News(0–5) + DCA Bonus(0–10) + Risk Adj(RR −8~+3) + Leverage Penalty(−15)
```

### 1. Growth Quality (0–35) — Steady growth with diminishing returns

Weighted long-term return (**excluding 1M/3M**): `6M×0.15 + 1Y×0.30 + 2Y×0.25 + 3Y×0.30`, then scaled with **diminishing returns** so high profit cannot dominate:

```
Growth Quality = 35 × (1 − e^(−long-term return % / 40))
```

Reference: 8% → 6.9 pts, 25% → 16.4, 50% → 24.5, 100% → 31.8, 200% → 34.4. Negative long-term return → 0.

### 2. Stability & Persistence (0–35) — Sustained profit, no deep drawdown

| Component | Points | Rule |
| :--- | :---: | :--- |
| Sustained positive returns | 0–15 | +5 each for 1Y/2Y/3Y positive |
| No deep drawdown | 0–12 | worst period ≥+5%→12, ≥0%→9, ≥−5%→6, ≥−15%→2, <−15%→0 |
| No recent crash | 0–8 | 1M>−3% & 3M>−5%→8; 1M>−8% & 3M>−10%→5; 1M>−15%→2; else 0 |

### 3. Income Bonus (0–15) — Effective yield with quality-tiered floors

Dividends are scored using the **effective yield** (`models.py`):

```
Effective Yield = Nominal Yield (trailing 12M Σdistribution ÷ latest NAV) × Income Quality
Income Quality (0–1) = amount-weighted average of the income-source ratio; records missing the ratio count as 50% income
```

Funds whose distributions come largely from principal (return of capital) are **discounted**:

```
Income Bonus = max( min(15, Effective Yield × 2.0), tier floor )
```

| Floor tier | Floor | Meaning |
| :--- | :---: | :--- |
| Complete (all ratios present, not all-principal) | 7 | Every distribution has a source ratio |
| No dividend data (distribution class) | 5 | Classified as distributing but no records |
| Half (has dividends, missing ratios) | 4 | Some/all distributions lack source ratios |
| Pure principal (all ratios = 0) | 3 | Every distribution is 100% principal |

An effective yield of 7.5% reaches the +15 cap; distributing funds always keep a basic bonus (never zeroed).

### 4. News Volume (0–5)

`min(5, # fund-specific news in 7 days × 1)` (capped at 5 items), counting only fund-specific matches to avoid cross-fund pollution. News is short-term noise, so it carries low weight.

### 5. DCA Bonus (0–10) — Systematic-investing experience

Simulates "investing USD 100 monthly for 12 months" (DCA, **estimated** — not real historical NAV):

```
DCA annual return % = (ending value + dividend cash − 1200) ÷ 1200 × 100
Ending value  = accumulated units × latest NAV; dividends credited as cash on units held at each month (not reinvested)
NAV path      = interpolated in log space from 1M/3M/6M/1Y return anchors over the past 12 months
```

```
DCA Bonus = clamp(DCA annual return % × 0.4, 0, 10) × (Stability score ÷ 35)
```

- A 25% DCA return reaches full points; negative returns score 0.
- **Stability gate**: multiplied by the stability score, so V-shaped high-volatility funds are discounted even with high DCA returns (consistent with "steady growth > high volatility").

### 6. Risk Adjustment (−8~+3) — RR risk-rating level

Source: TDCC `fund-basic/query-details` risk-reward level (RR1–RR5).

| RR | RR1 | RR2 | RR3 | RR4 | RR5 |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Adj | +3 | +1.5 | 0 | −4 | −8 |

High-risk (RR4/RR5) funds are penalized as unsuitable for long-term investing; low-risk (RR1/RR2) funds are rewarded.

### 7. Leverage Penalty (−15)

Names containing `槓桿｜放空｜反向｜Inverse｜Leveraged｜Daily Nx` (leveraged/inverse instruments) → −15. Currency-hedged classes (**Hedged/對沖**) are NOT penalized.

### Tunable Parameters (env vars)

`GROWTH_MAX`, `GROWTH_DECAY`, `STABILITY_MAX_NEW`, `INCOME_BONUS`, `INCOME_YIELD_PER_POINT`, `INCOME_QUALITY_UNKNOWN`, `INCOME_BONUS_COMPLETE_FLOOR`, `INCOME_BONUS_NO_DATA_FLOOR`, `INCOME_BONUS_MISSING_FLOOR`, `INCOME_BONUS_PRINCIPAL_FLOOR`, `DCA_BONUS_MAX`, `DCA_RETURN_PER_POINT`, `DCA_INVEST_MONTHLY`, `RISK_BONUS_RR1..RR5`, `LEVERAGE_PENALTY`.

### Ranking

Sorted by preliminary score ↓ → long-term return ↓ → name ↑ (deterministic, reproducible). The top funds then receive LLM deep analysis (40/40/20 value score), with a combined rating for final presentation.

## Tax & Asset Allocation Notes

All targets in this project comply with Taiwan's Income Basic Tax Act (AMT); capital gains and distributions are 100% classified as offshore income.

### Three Key Tax Advantages

1. NTD 1M reporting threshold: households whose total annual offshore income is below NTD 1,000,000 do not need to include it in the basic income amount.
2. NTD 7.5M exemption: households above the 1M threshold, combined with other basic income items, enjoy an annual NTD 7,500,000 exemption.
3. No NHI supplementary premium: offshore-fund distributions are exempt from the 2.11% NHI supplementary premium.

### Accumulation vs Distribution Classes

| Class | Characteristic | Suggested use |
| :--- | :--- | :--- |
| Accumulation (Acc) | Income reinvested; gains deferred | Long-term growth; avoid crossing the annual reporting threshold |
| Distribution (Dis) | Generates immediate offshore-income cash flow | Make use of the NTD 1M reporting threshold and NTD 7.5M exemption |

### Target Users

The tax advantages are especially suited to high-net-worth investors in the 20%–40% tax brackets with offshore-allocation needs, as a tax-planning reference tool.

## Report Page Structure

The daily report page (docs/index.html, published via GitHub Pages) includes:

- **Fund ranking table**: top 500 by preliminary score; columns = rank, fund name (with code), preliminary score, channel icons; supports name/code search and channel filtering.
- **Per-fund deep dive**: collapsible cards with news summary, score rationale, deep score, rating, buying pattern, pros/cons, tax labels, and recent trend.
- **History calendar**: browse past daily reports via a calendar (docs/archive/).
- **Trend comparison**: case trend charts and multi-day side-by-side comparison (docs/trends.html).
- **Full ranking**: complete fund ranking table (docs/ranking.html).
- **System health**: daily pipeline status and LLM provider usage (docs/health.html).
- **Tax notes & disclaimer**: offshore-income category, NHI supplementary premium exemption, exemption amount, and data sources.

## Automation & Quality Requirements

- Two-stage filtering for cost control: rule-based pre-filtering (price change, news volume, flows) narrows the watchlist before deep AI analysis, limiting LLM token usage.
- Output consistency: AI analysis must follow the fixed scoring matrix and structured format so daily reports stay stable and comparable.
- Source stability: prefer structurally stable public data sources to reduce maintenance cost from site redesigns.
- Error handling: scraping failures, missing NAVs, or news shortfalls must degrade gracefully or alert — never publish an incomplete report silently.

## Development Roadmap

| Milestone | Scope | Deliverable | Status |
| :--- | :--- | :--- | :--- |
| M1 Data Pipeline | Define target fund list (3 channels / USD / offshore income), NAV & news fetching | Target list and daily raw dataset | Done |
| M2 AI Analysis Module | Preliminary ranking, Gemini deep analysis (scoring, sentiment, buying strategy, pros/cons) | Structured AI analysis output | Done |
| M3 Report & Schedule | Static web report generation and daily 06:00 scheduled publishing | Daily report pages | Done |
| M4 History Archive & Calendar | Historical archive pages + calendar browsing (latest/historical switching) | Historical report calendar | Done |
| M5 Trend Comparison | Score/rank trends over time, multi-day side-by-side comparison | Case trend charts + comparison table + `trends.html` | Done |
| M6 Quality & UX | Slim homepage + channel filter, score calibration, news quality, trend deepening | Lightweight index + `ranking.html` + calibration | Done |

Detailed planning for each milestone will be expanded later using the "grill-with-docs" skill.

## Planned Directory Structure

```
├── .github/workflows/        Daily 06:00 schedule
├── src/alphafund/            M1–M6 package (tdcc/news/scoring/llm/analyzer/report/trends/health/pipeline/cli)
├── scripts/                  Entry points (run_m1.py)
├── data/
│   └── history/<date>/       Daily snapshots (snapshot / nav / news / universe / analysis, .json.gz)
├── docs/
│   ├── index.html            Daily report page (published via GitHub Pages, with calendar)
│   ├── ranking.html          Full ranking table (latest full universe, channel filter)
│   ├── trends.html           Trend comparison page
│   ├── health.html           System health page (daily status + provider usage)
│   ├── archive/<date>.html   Historical report archive (calendar browsing)
│   ├── adr/                  Architecture decision records
│   ├── m1-design.md          M1 design document
│   ├── m2-design.md          M2 design document
│   └── m3-design.md          M3 design document
├── tests/                    Unit tests (fixtures)
├── README.md                 Traditional Chinese (default)
├── README.en.md              English
└── LICENSE                   MIT
```

## Disclaimer

1. Not investment advice: all content produced by this project (news summaries, AI value scores, pros/cons analysis, and buying-pattern recommendations) is generated by automated programs and AI models, for academic research and personal asset-management reference only. It does not constitute solicitation, an offer, or a basis for any investment decision.
2. Data latency: fund NAV, news, and channel information come from third-party public sources; the project does not guarantee timeliness, completeness, or absolute accuracy.
3. Risk at your own discretion: investors should make independent judgments and carefully assess their own risk tolerance and tax situation. Offshore-fund investing involves currency and market volatility risks; past performance is not a guarantee of future results.

## Related Data Sources

- [TDCC Fund Information Observation Platform](https://www.fundclear.com.tw)
- [MoneyDJ Fund Channel](https://www.moneydj.com)
- [GitHub Pages](https://pages.github.com)

## Contributing

Pull requests and feature requests are welcome:

1. **Data pipeline** — add or fix target fund list and data sources.
2. **Analysis modules** — improve the scoring matrix, news filtering, or AI prompts.
3. **Documentation** — fix typos, fill gaps, improve quality.

Flow: Fork this project → develop → submit a PR → I review and merge.

## License

MIT
