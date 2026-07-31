"""LLM 客戶端抽象：支援 Gemini API 與 OpenRouter 兩供應商。

供應商切換：`LLM_PROVIDER`（gemini 預設 | openrouter）。
兩者皆提供 `generate_json(system_prompt, user_prompt) -> dict` 介面；
429（額度/速率限制）→ `QuotaExceeded`，由 pipeline 優雅降級。
"""
from __future__ import annotations

import json
import logging
from typing import Protocol

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed

from .config import (
    GEMINI_API_KEY,
    GEMINI_API_URL,
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    LLM_PROVIDER,
    OPENROUTER_API_KEY,
    OPENROUTER_API_URL,
    OPENROUTER_MODEL,
)

logger = logging.getLogger(__name__)

_RETRYABLE = (httpx.TransportError, httpx.TimeoutException)


def _retry_predicate(exc: BaseException) -> bool:
    """傳輸/逾時錯誤，或 HTTP 5xx（瞬態伺服器錯誤）才重試。"""
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


_RETRY_ARGS = {
    "retry": retry_if_exception(_retry_predicate),
    "stop": stop_after_attempt(3),
    "wait": wait_fixed(2),
    "reraise": True,
}


class QuotaExceeded(RuntimeError):
    """LLM API 額度/速率限制用罄（429）。"""


class LLMClient(Protocol):
    """LLM 供應商統一介面。"""

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict: ...

    def close(self) -> None: ...


def _extract_json(text: str) -> dict:
    """自回應文字解析 JSON（容忍 markdown code fence）。"""
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return json.loads(t)


class GeminiClient:
    """Gemini API（Free Tier）。"""

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
        self._api_key = api_key
        self._temperature = temperature
        self._client = httpx.Client(timeout=timeout, transport=transport)
        self._url = f"{GEMINI_API_URL}/{model}:generateContent"

    @retry(**_RETRY_ARGS)
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
        return _extract_json(text)

    def close(self) -> None:
        self._client.close()


class OpenRouterClient:
    """OpenRouter（單一 API 接多模型；支援免費與付費模型）。"""

    def __init__(
        self,
        api_key: str = OPENROUTER_API_KEY,
        model: str = OPENROUTER_MODEL,
        temperature: float = GEMINI_TEMPERATURE,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError(
                "未設定 OPENROUTER_API_KEY：請至 https://openrouter.ai/keys 建立 "
                "並設為環境變數 OPENROUTER_API_KEY"
            )
        self._model = model
        self._temperature = temperature
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def _request(self, model: str | None, use_format: bool) -> dict:
        payload: dict = {
            "model": model or self._model,
            "messages": self._messages,
            "temperature": self._temperature,
        }
        if use_format:
            payload["response_format"] = {"type": "json_object"}
        return payload

    @retry(**_RETRY_ARGS)
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        self._messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        resp = self._client.post(
            OPENROUTER_API_URL,
            headers=self._headers,
            json=self._request(None, use_format=True),
        )
        # 部分模型不支援 response_format（400）→ 去格式重試一次
        if resp.status_code == 400 and "response_format" in resp.text.lower():
            logger.warning("模型不支援 JSON mode，改用無格式重試")
            resp = self._client.post(
                OPENROUTER_API_URL,
                headers=self._headers,
                json=self._request(None, use_format=False),
            )
        if resp.status_code == 429:
            logger.warning("OpenRouter 額度/速率限制（429）：%s", resp.text[:200])
            raise QuotaExceeded("OpenRouter 額度已用罄（429）")
        resp.raise_for_status()
        data = resp.json()
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"OpenRouter 回應格式異常: {data}") from exc
        return _extract_json(text)

    def close(self) -> None:
        self._client.close()


def get_llm_client() -> LLMClient:
    """依 LLM_PROVIDER 建立對應客戶端。"""
    if LLM_PROVIDER == "openrouter":
        return OpenRouterClient()
    return GeminiClient()
