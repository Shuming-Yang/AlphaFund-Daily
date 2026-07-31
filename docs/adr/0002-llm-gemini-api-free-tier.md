# LLM 供應商：Gemini API Free Tier，零付費

AI 評分與報告撰寫使用 Gemini API 的 Free Tier（無 billing、無信用卡），模型選 Flash 等級。免費額度以 RPM/RPD 計，RPD 每日太平洋時間午夜重置；額度用罄時 API 回傳 429，管道需優雅降級（該檔標記分析延遲，隔日補上）。

不選擇付費方案或 Google AI Pro 的 Cloud credits：使用者要求完全不付費，且每日約 40–60 次呼叫遠低於 Flash 免費額度上限。此決定將分析容量鎖定在免費額度內，基金清單擴大時需依賴規則式前置過濾控制 LLM 呼叫量；免費額度下 Google 可能使用資料改善產品。
