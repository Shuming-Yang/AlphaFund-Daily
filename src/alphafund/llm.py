"""Gemini API 客戶端（Free Tier，ADR-0002）。

- 使用 generateContent + responseMimeType=application/json（JSON mode）。
- 額度用罄（HTTP 429 RESOURCE_EXHAUSTED）→ 拋 QuotaExceeded，由 pipeline 優雅降級。
- 其餘瞬態錯誤以 tenacity 重試。
"""
from __future__ import annotations

import json
import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from .config import GEMINI_API_KEY, GEMINI_API_URL, GEMINI_MODEL, GEMINI_TEMPERATURE

logger = logging.getLogger(__name__)

_RETRYABLE = (httpx.TransportError, httpx.TimeoutException)


class QuotaExceeded(RuntimeError):
    """Gemini API 免費額度用罄（429）。"""


class GeminiClient:
    def __init__(
        self,
        api_key: str = GEMINI_API_KEY,
        model: str = GEMINI_MODEL,
        temperature: float = GEMINI_TEMPERATURE,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError(
                "未設定 GEMINI_API_KEY：請至 https://aistudio.google.com 建立免費 API Key "
                "並設為環境變數 GEMINI_API_KEY"
            )
        self._model = model
        self._temperature = temperature
        self._api_key = api_key
        self._client = httpx.Client(timeout=timeout, transport=transport)
        self._url = f"{GEMINI_API_URL}/{model}:generateContent"

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        reraise=True,
    )
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": self._temperature,
            },
        }
        resp = self._client.post(
            self._url, params={"key": self._api_key}, json=payload
        )
        if resp.status_code == 429:
            logger.warning("Gemini API 額度用罄（429）：%s", resp.text[:200])
            raise QuotaExceeded("Gemini 免費額度已用罄（429）")
        resp.raise_for_status()
        data = resp.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Gemini 回應格式異常: {data}") from exc
        return json.loads(text)

    def close(self) -> None:
        self._client.close()
