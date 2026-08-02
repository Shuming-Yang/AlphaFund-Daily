"""Gemini 客戶端與分析 prompt/解析測試（mock，不觸網）。"""
from __future__ import annotations

import json

import httpx
import pytest

from alphafund.analyzer import (
    SYSTEM_PROMPT,
    build_user_prompt,
    parse_deep_analysis,
)
from alphafund.llm import (
    CloudflareClient,
    FallbackLLM,
    GeminiClient,
    GroqClient,
    NvidiaNimClient,
    OpenRouterClient,
    QuotaExceeded,
    _extract_json,
)
from alphafund.models import Fund, NewsItem


def _make_client(handler):
    return GeminiClient(
        api_key="test-key",
        model="gemini-test",
        transport=httpx.MockTransport(handler),
    )


def _make_or_client(handler):
    return OpenRouterClient(
        api_key="or-test",
        model="google/gemma-test:free",
        transport=httpx.MockTransport(handler),
    )


# --- GeminiClient ---

def test_generate_json_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models/gemini-test:generateContent")
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps({"value_score": 88})}]}}]},
        )

    client = _make_client(handler)
    out = client.generate_json("sys", "user")
    assert out == {"value_score": 88}


def test_generate_json_quota_exhausted():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "RESOURCE_EXHAUSTED"}})

    client = _make_client(handler)
    with pytest.raises(QuotaExceeded):
        client.generate_json("sys", "user")


def test_client_requires_key():
    with pytest.raises(ValueError):
        GeminiClient(api_key="")
    with pytest.raises(ValueError):
        OpenRouterClient(api_key="")


def test_extract_json_strips_fence():
    text = '```json\n{"a": 1}\n```'
    assert _extract_json(text) == {"a": 1}


def test_openrouter_generate_json_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "google/gemma-test:free"
        assert body["response_format"] == {"type": "json_object"}
        assert body["max_tokens"] == 2048
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps({"value_score": 77})}}]},
        )

    client = _make_or_client(handler)
    out = client.generate_json("sys", "user")
    assert out == {"value_score": 77}


def test_fallback_llm_switches_on_json_decode_error(monkeypatch):
    """供應商輸出無法解析（截斷）→ 切換下一家。"""
    import json as _json

    class FakeBroken:
        def generate_json(self, system, user):
            raise _json.JSONDecodeError("Unterminated string", "doc", 0)

        def close(self):
            pass

    class FakeOk:
        def generate_json(self, system, user):
            return {"ok": True}

        def close(self):
            pass

    built = [FakeBroken(), FakeOk()]
    calls = []

    def fake_build(name):
        calls.append(name)
        return built[len(calls) - 1]

    monkeypatch.setattr("alphafund.llm.build_client", fake_build)
    fb = FallbackLLM(providers=["a", "b"])
    out = fb.generate_json("sys", "user")
    assert out == {"ok": True}
    assert calls == ["a", "b"]


def test_openrouter_retries_without_format_on_400():
    """模型不支援 response_format → 400 時去格式重試。"""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(400, text="response_format not supported")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '```json\n{"ok": true}\n```'}}]},
        )

    client = _make_or_client(handler)
    out = client.generate_json("sys", "user")
    assert out == {"ok": True}
    assert len(calls) == 2
    assert "response_format" not in calls[1]


def test_openrouter_quota_exhausted():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    client = _make_or_client(handler)
    with pytest.raises(QuotaExceeded):
        client.generate_json("sys", "user")


def test_groq_client_config():
    client = GroqClient(
        api_key="groq-test",
        model="llama-3.3-70b-versatile",
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"ok": 1}'}}]},
            )
        ),
    )
    assert client.generate_json("s", "u") == {"ok": 1}


def test_cloudflare_client_config_and_url():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": 1}'}}]},
        )

    client = CloudflareClient(
        account_id="acc123",
        api_key="cf-token",
        model="@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        transport=httpx.MockTransport(handler),
    )
    assert client.generate_json("s", "u") == {"ok": 1}
    assert "/accounts/acc123/ai/v1/chat/completions" in captured["url"]


def test_cloudflare_client_requires_account_id():
    with pytest.raises(ValueError):
        CloudflareClient(account_id="", api_key="x")


def test_nvidia_nim_client_config():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": 1}'}}]},
        )

    client = NvidiaNimClient(
        api_key="nv-test",
        model="meta/llama-3.3-70b-instruct",
        transport=httpx.MockTransport(handler),
    )
    assert client.generate_json("s", "u") == {"ok": 1}
    assert "integrate.api.nvidia.com/v1/chat/completions" in captured["url"]


def test_nvidia_nim_requires_key():
    with pytest.raises(ValueError):
        NvidiaNimClient(api_key="")


def test_fallback_llm_switches_on_429(monkeypatch):
    """第一家 429 → 自動切換第二家。"""
    calls = {"n": 0}

    class FakeQuota:
        def generate_json(self, system, user):
            raise QuotaExceeded("quota")

        def close(self):
            pass

    class FakeOk:
        def generate_json(self, system, user):
            return {"ok": True}

        def close(self):
            pass

    built = [FakeQuota(), FakeOk()]

    def fake_build(name):
        c = built[calls["n"]]
        calls["n"] += 1
        return c

    monkeypatch.setattr("alphafund.llm.build_client", fake_build)
    fb = FallbackLLM(providers=["a", "b"])
    out = fb.generate_json("sys", "user")
    assert out == {"ok": True}
    assert calls["n"] == 2  # 建了兩家


def test_fallback_llm_switches_on_401(monkeypatch):
    """401（無效/未授權 key）也應切換下一家。"""
    import httpx as _h

    class Fake401:
        def generate_json(self, system, user):
            raise _h.HTTPStatusError(
                "401",
                request=_h.Request("POST", "http://x"),
                response=_h.Response(401),
            )

        def close(self):
            pass

    class FakeOk:
        def generate_json(self, system, user):
            return {"ok": True}

        def close(self):
            pass

    calls = []

    def fake_build(name):
        calls.append(name)
        return Fake401() if name == "bad" else FakeOk()

    monkeypatch.setattr("alphafund.llm.build_client", fake_build)
    fb = FallbackLLM(providers=["bad", "ok"])
    out = fb.generate_json("sys", "user")
    assert out == {"ok": True}
    assert calls == ["bad", "ok"]


def test_fallback_llm_skips_unconfigured_provider(monkeypatch):
    """未設定 key 的供應商應被跳過，而非中斷切換。"""
    calls = []

    def fake_build(name):
        calls.append(name)
        if name == "no-key":
            raise ValueError("未設定 xxx API Key")
        return FakeOk()

    class FakeOk:
        def generate_json(self, system, user):
            return {"ok": True}

        def close(self):
            pass

    monkeypatch.setattr("alphafund.llm.build_client", fake_build)
    fb = FallbackLLM(providers=["no-key", "ok"])
    out = fb.generate_json("sys", "user")
    assert out == {"ok": True}
    assert calls == ["no-key", "ok"]


def test_fallback_llm_raises_when_all_exhausted(monkeypatch):
    class FakeQuota:
        def generate_json(self, system, user):
            raise QuotaExceeded("quota")

        def close(self):
            pass

    def fake_build(name):
        return FakeQuota()

    monkeypatch.setattr("alphafund.llm.build_client", fake_build)
    fb = FallbackLLM(providers=["a", "b"])
    with pytest.raises(QuotaExceeded):
        fb.generate_json("sys", "user")


# --- analyzer ---

def test_build_user_prompt_includes_fund_data():
    f = Fund(
        fund_code="0352",
        name="富蘭克林坦伯頓全球投資系列-日本基金美元A (acc)股",
        currency="USD",
        channels=["元大證券", "匯豐銀行"],
        nav="15.64",
        nav_date="2026/07/30",
        returns={"navValue5": "1.0", "navValue8": "10.0"},
    )
    prompt = build_user_prompt(f, [], "2026-08-01")
    assert "0352" in prompt
    assert "15.64" in prompt
    assert "元大證券" in prompt
    assert "無近 24 小時相關新聞" in prompt


def test_build_user_prompt_includes_news():
    f = Fund(fund_code="A", name="測試基金", currency="USD")
    news = [NewsItem(title="測試基金 報酬亮眼", source="鉅亨網", published_at="Fri, 31 Jul 2026 04:27:05 GMT")]
    prompt = build_user_prompt(f, news, "2026-08-01")
    assert "鉅亨網" in prompt
    assert "報酬亮眼" in prompt


def test_parse_deep_analysis():
    raw = {
        "news_summary": ["重點一"],
        "market_sentiment": "Positive",
        "value_score": 85,
        "score_rationale": "理由",
        "recommended_strategy": "定期定額",
        "strategy_explanation": "原因",
        "pros": ["優勢一"],
        "cons": ["風險一"],
        "overall_rating": "值得關注",
    }
    da = parse_deep_analysis(raw, "0352", "2026-08-01")
    assert da.fund_code == "0352"
    assert da.value_score == 85
    assert da.market_sentiment == "Positive"
    assert da.overall_rating == "強力推薦"  # 分數驅動（85 → 強力推薦）
    assert da.llm_rating == "值得關注"
    assert da.recommended_strategy == "定期定額"


def test_parse_deep_analysis_fallback_and_clamp():
    da = parse_deep_analysis(
        {"market_sentiment": "weird", "value_score": "abc", "value_extra": 999},
        "X",
        "2026-08-01",
    )
    assert da.market_sentiment == "Neutral"
    assert da.value_score == 0.0
    assert da.pros == []


def test_parse_deep_analysis_handles_non_dict():
    da = parse_deep_analysis(["not", "a", "dict"], "X", "2026-08-01")
    assert da.fund_code == "X"
    assert "格式異常" in da.score_rationale
    assert da.value_score == 0.0


# --- WP2 評分校準（ADR-0010）---

def test_system_prompt_has_calibration_guidance():
    assert "評分校準指引" in SYSTEM_PROMPT
    assert "55–85" in SYSTEM_PROMPT
    assert "避免將不同標的都評為相近分數" in SYSTEM_PROMPT
    assert "評級決策指引" in SYSTEM_PROMPT
    assert "強力推薦" in SYSTEM_PROMPT and "暫時避開" in SYSTEM_PROMPT


def test_parse_rating_score_driven_keeps_llm_rating():
    # 評級一律由 value_score 決定（85 → 強力推薦）；LLM 原始評級存 llm_rating
    da = parse_deep_analysis(
        {"value_score": 85, "overall_rating": "值得關注"}, "0352", "2026-08-01"
    )
    assert da.overall_rating == "強力推薦"
    assert da.llm_rating == "值得關注"


def test_parse_rating_strong_rec_with_low_score_overridden():
    # 強力推薦 + 30 分 → 覆寫為門檻評級（暫時避開）
    da = parse_deep_analysis(
        {"value_score": 30, "overall_rating": "強力推薦"}, "X", "2026-08-01"
    )
    assert da.overall_rating == "暫時避開"


def test_parse_rating_avoid_with_high_score_overridden():
    # 暫時避開 + 85 分 → 覆寫為門檻評級（強力推薦）
    da = parse_deep_analysis(
        {"value_score": 85, "overall_rating": "暫時避開"}, "X", "2026-08-01"
    )
    assert da.overall_rating == "強力推薦"


def test_parse_rating_empty_derived_from_score():
    da = parse_deep_analysis({"value_score": 88}, "X", "2026-08-01")
    assert da.overall_rating == "強力推薦"
    da = parse_deep_analysis({"value_score": 55}, "X", "2026-08-01")
    assert da.overall_rating == "中立觀望"
    da = parse_deep_analysis({"value_score": 45}, "X", "2026-08-01")
    assert da.overall_rating == "暫時避開"


def test_parse_income_suitability():
    raw = {
        "market_sentiment": "Neutral", "value_score": 75,
        "overall_rating": "值得關注", "income_suitability": "適合",
        "recommended_strategy": "定期定額",
    }
    da = parse_deep_analysis(raw, "X", "2026-08-01")
    assert da.income_suitability == "適合"
    assert da.overall_rating == "值得關注"  # 75 → 值得關注（70-84）
