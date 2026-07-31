# LLM 供應商鏈：429 自動切換（Fallback）

單一供應商在免費額度（或速率限制）耗盡時會 429，若不做切換，當日深度分析會大量略過。

決策：`FallbackLLM` 依 `LLM_PROVIDER_CHAIN`（預設 `openrouter,gemini,groq`）依序嘗試；某家 429 時**自動切換下一家**，全數用罄才標記 `quota_skipped`。每家實作統一 `generate_json` 介面（LLMClient Protocol）。

供應商與免費方案：
| 供應商 | 模型 | 免費額度 |
| :--- | :--- | :--- |
| OpenRouter | gemma-4-26b-a4b-it:free | 50 次/日/模型 |
| Gemini | gemini-3.6-flash | RPD≈17/日 |
| Groq | llama-3.3-70b-versatile | ~14,400 次/日 |

備援考量：
- **GitHub Copilot** 未採納：GitHub Models 正在退役（410 brownout），Copilot 自身 API 用於批次分析屬灰色地帶。
- 第 4 家（如 Mistral / Cloudflare Workers AI）可於鏈中擴充，目前三家已覆蓋免費額度互補。
