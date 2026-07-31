"""LLM 客戶端抽象與供應商鏈。

- `GeminiClient` / `OpenRouterClient` / `GroqClient`：各供應商實作，皆提供
  `generate_json(system_prompt, user_prompt) -> dict` 介面。
- `FallbackLLM`：依 `LLM_PROVIDER_CHAIN` 依序嘗試；某家 429（額度/速率限制）
  自動切換下一家，全數用罄才拋 `QuotaExceeded`（ADR-0007）。
"""
from __future__ import annotations

import json
import logging
from typing import Protocol

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed

from .config import (
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_API_TOKEN,
    CLOUDFLARE_API_URL,
    CLOUDFLARE_MODEL,
    GEMINI_API_KEY,
    GEMINI_API_URL,
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    GROQ_API_KEY,
    GROQ_API_URL,
    GROQ_MODEL,
    LLM_PROVIDER_CHAIN,
    OPENROUTER_API_KEY,
    OPENROUTER_API_URL,
    OPENROUTER_MODEL,
)

logger = logging.getLogger(__name__)


class QuotaExceeded(RuntimeError):
    """LLM API 額度/速率限制用罄（429）。"""


class LLMClient(Protocol):
    """LLM 供應商統一介面。"""

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict: ...

    def close(self) -> None: ...


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


class OpenAICompatClient:
    """OpenAI-compatible chat completions 基底（OpenRouter / Groq）。"""

    def __init__(
        self,
        api_key: str,
        url: str,
        model: str,
        temperature: float = GEMINI_TEMPERATURE,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError(f"未設定 {self.key_env()} API Key")
        self._model = model
        self._temperature = temperature
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._url = url
        self._client = httpx.Client(timeout=timeout, transport=transport)
        self._messages: list[dict[str, str]] = []

    def key_env(self) -> str:
        return "OPENROUTER_API_KEY"  # 子類別覆寫

    def _payload(self, use_format: bool) -> dict:
        payload: dict = {
            "model": self._model,
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
            self._url, headers=self._headers, json=self._payload(use_format=True)
        )
        # 部分模型不支援 response_format（400）→ 去格式重試一次
        if resp.status_code == 400 and "response_format" in resp.text.lower():
            logger.warning("模型不支援 JSON mode，改用無格式重試")
            resp = self._client.post(
                self._url, headers=self._headers, json=self._payload(use_format=False)
            )
        if resp.status_code == 429:
            logger.warning("%s 額度/速率限制（429）：%s", self.__class__.__name__, resp.text[:200])
            raise QuotaExceeded(f"{self.__class__.__name__} 額度已用罄（429）")
        resp.raise_for_status()
        data = resp.json()
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"{self.__class__.__name__} 回應格式異常: {data}") from exc
        return _extract_json(text)

    def close(self) -> None:
        self._client.close()


class OpenRouterClient(OpenAICompatClient):
    """OpenRouter（單一 API 接多模型；免費與付費）。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("api_key", OPENROUTER_API_KEY)
        kwargs.setdefault("url", OPENROUTER_API_URL)
        kwargs.setdefault("model", OPENROUTER_MODEL)
        super().__init__(**kwargs)

    def key_env(self) -> str:
        return "OPENROUTER_API_KEY"


class GroqClient(OpenAICompatClient):
    """Groq（免費 tier，llama-3.3-70b）。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("api_key", GROQ_API_KEY)
        kwargs.setdefault("url", GROQ_API_URL)
        kwargs.setdefault("model", GROQ_MODEL)
        super().__init__(**kwargs)

    def key_env(self) -> str:
        return "GROQ_API_KEY"


class CloudflareClient(OpenAICompatClient):
    """Cloudflare Workers AI（免費 tier，10,000 neurons/日）。

    OpenAI 相容端點：/accounts/{account_id}/ai/v1/chat/completions。
    """

    def __init__(self, **kwargs):
        account_id = kwargs.pop("account_id", None) or CLOUDFLARE_ACCOUNT_ID
        if not account_id:
            raise ValueError("未設定 CLOUDFLARE_ACCOUNT_ID（Cloudflare 帳號 ID）")
        kwargs.setdefault("api_key", CLOUDFLARE_API_TOKEN)
        kwargs.setdefault(
            "url", f"{CLOUDFLARE_API_URL}/accounts/{account_id}/ai/v1/chat/completions"
        )
        kwargs.setdefault("model", CLOUDFLARE_MODEL)
        super().__init__(**kwargs)

    def key_env(self) -> str:
        return "CLOUDFLARE_API_TOKEN"


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


def build_client(provider: str) -> LLMClient:
    """依供應商名稱建立客戶端。"""
    if provider == "gemini":
        return GeminiClient()
    if provider == "groq":
        return GroqClient()
    if provider == "cloudflare":
        return CloudflareClient()
    if provider == "openrouter":
        return OpenRouterClient()
    raise ValueError(f"未知 LLM 供應商: {provider}")


class FallbackLLM:
    """供應商鏈：429（額度）或 401/403（無效/未授權 key）時自動切換下一家（ADR-0007）。"""

    def __init__(self, providers: list[str] | None = None) -> None:
        self._providers = providers or list(LLM_PROVIDER_CHAIN)
        if not self._providers:
            raise ValueError("LLM_PROVIDER_CHAIN 為空")
        self._active = 0
        self._client: LLMClient | None = None

    def _should_switch(self, exc: BaseException) -> bool:
        if isinstance(exc, QuotaExceeded):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in (401, 403)
        return False

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        while True:
            if self._client is None:
                try:
                    self._client = build_client(self._providers[self._active])
                except ValueError as exc:
                    # 未設定 key 的供應商 → 跳過
                    logger.warning("供應商 %s 未設定，跳過（%s）", self._providers[self._active], exc)
                    self._active += 1
                    if self._active >= len(self._providers):
                        raise
                    continue
            try:
                return self._client.generate_json(system_prompt, user_prompt)
            except (QuotaExceeded, httpx.HTTPStatusError) as exc:
                if not self._should_switch(exc):
                    raise
                logger.warning(
                    "供應商 %s 不可用（%s）→ 切換備援",
                    self._providers[self._active],
                    getattr(exc, "response", exc),
                )
                self._client.close()
                self._client = None
                self._active += 1
                if self._active >= len(self._providers):
                    raise
                continue

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    @property
    def provider(self) -> str:
        return self._providers[self._active]


def get_llm_client() -> FallbackLLM:
    """建立供應商鏈客戶端（依 LLM_PROVIDER_CHAIN）。"""
    return FallbackLLM()
