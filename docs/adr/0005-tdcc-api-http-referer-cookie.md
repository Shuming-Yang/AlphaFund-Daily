# TDCC API 以純 HTTP 存取（cookies + Referer）

Spike 初期直接 POST TDCC API 一律回傳 403，一度判定為 reCAPTCHA 反爬保護而考慮改用 Playwright 無頭瀏覽器或轉向 MoneyDJ。深入測試後發現：403 主因是**缺少對應頁面的 Referer**（與 session cookie）。

決策：使用 `httpx` 維持 cookie session —— 先 GET 首頁暖機，POST 時帶對應頁面的 `Referer`（基金搜尋 / 機構查詢 / 銷售基金），即可穩定存取，**無需瀏覽器依賴**。此舉大幅降低 CI 體積與失敗面。

此決定依賴 TDCC 後端當前的 Referer 檢查行為；若 TDCC 未來強化防護（啟用嚴格 reCAPTCHA 驗證或封鎖），需回到 Playwright 方案（見 `m1-design.md`）。
