# LLM 供應商：OpenRouter 免費模型（gemma-4-26b:free）

實測發現 Gemini API Free Tier 對 `gemini-3.6-flash` 的每日請求上限（RPD）僅約 **17 次/日**，不足以支應每日 top-25 深度分析（需 25 次）。使用者 OpenRouter 帳號為 **free tier、無 credits**（`total_credits=0`），無法使用付費 DeepSeek V4 Flash（成本雖極低 $0.14/$0.28 每 M token）。

決策：`LLM_PROVIDER` 預設改為 **openrouter**，模型 `google/gemma-4-26b-a4b-it:free`（OpenRouter 免費，50 次/日/模型，足夠每日分析）。Gemini 仍可經 `LLM_PROVIDER=gemini` 切回（免費額度足夠時）。

代價：gemma-4-26b 分析品質較 gemini-flash 簡樸（評分理由較簡短）；零成本原則（ADR-0002）仍維持。
