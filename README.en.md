[繁體中文](./README.md) · [**English**](./README.en.md)

---

# AlphaFund-Daily — Daily AI Offshore Fund Research & Selection Report

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

Only the following two share classes are kept:

- USD
- TWD

All other currencies (ZAR, AUD, EUR, CNY, JPY, etc.) are excluded to reduce exchange-rate noise and focus on mainstream reserve/settlement currencies.

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
| Currency | Share classes other than USD / TWD |
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

The daily report page includes the following modules:

- Full ranking table sorted by AI Value Score.
- Per-fund deep dive: news summary, score rationale, buying pattern, and pros/cons.
- Tax labels: offshore-income category, NHI supplementary premium exemption, applicable exemption amount.
- Channel hints: which channel offers better fees or promotions.
- Report date and data-source statement.

## Automation & Quality Requirements

- Two-stage filtering for cost control: rule-based pre-filtering (price change, news volume, flows) narrows the watchlist before deep AI analysis, limiting LLM token usage.
- Output consistency: AI analysis must follow the fixed scoring matrix and structured format so daily reports stay stable and comparable.
- Source stability: prefer structurally stable public data sources to reduce maintenance cost from site redesigns.
- Error handling: scraping failures, missing NAVs, or news shortfalls must degrade gracefully or alert — never publish an incomplete report silently.

## Development Roadmap

| Milestone | Scope | Deliverable |
| :--- | :--- | :--- |
| M1 Data Pipeline | Define target fund list (3 channels / USD+TWD / offshore income), NAV & news fetching | Target list and daily raw dataset |
| M2 AI Analysis Module | Scoring matrix, sentiment classification, buying strategy, pros/cons generation | Structured AI analysis output |
| M3 Report & Schedule | Static web report generation and daily 06:00 scheduled publishing | Daily report pages |
| M4 Quality Tuning | Score calibration, cost optimization, anomaly alerts, historical tracking | Stable, running automation |

Detailed planning for each milestone will be expanded later using the "grill-with-docs" skill.

## Planned Directory Structure

```
├── .github/workflows/        Daily 06:00 schedule
├── config/                   Target fund list (3 channels / USD+TWD / offshore income)
├── scripts/                  NAV & news fetching, AI analysis, report generation
├── docs/                     Static report pages (published via GitHub Pages)
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
