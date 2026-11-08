import json
from types import SimpleNamespace

import httpx
import pytest
import requests
from openai import OpenAI

from brand_research.config import Settings, load_settings
from brand_research.limits import Budget, LimitReached, ProviderError
from brand_research.providers import OpenAIExtractor, SerpApiSearch, source_rank


class Session:
    def __init__(self, payload=None, status=200, error=None):
        self.payload = payload
        self.status = status
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return SimpleNamespace(status_code=self.status, json=lambda: self.payload)


def test_serpapi_request_and_public_result_filtering():
    rows = [
        {
            "title": "History",
            "link": "https://auroratea.example/history",
            "snippet": "Aurora Tea was founded in India in 1998.",
        },
        {"link": "https://linkedin.com/in/private-person", "snippet": "Not a company page."},
        {
            "link": "https://linkedin.com/company/aurora",
            "snippet": "A public company search excerpt.",
        },
        {"link": "javascript:bad", "snippet": "unsafe"},
        {"link": "https://example.com/no-evidence"},
    ]
    session = Session({"organic_results": rows})
    budget = Budget()
    provider = SerpApiSearch(Settings("test-key", "test-key"), budget, session)
    sources = provider.search("Aurora Tea history", "Aurora Tea", "", recent=True)
    assert len(sources) == 2
    assert sources[0].tier == 1
    url, kwargs = session.calls[0]
    assert url == "https://serpapi.com/search.json"
    assert kwargs["params"]["engine"] == "google"
    assert kwargs["params"]["tbs"] == "qdr:y"
    assert kwargs["allow_redirects"] is False
    assert budget.searches == 1


@pytest.mark.parametrize("case", ["quota", "api_error", "network", "bad_shape"])
def test_serpapi_failures_are_counted_and_secrets_are_redacted(case):
    secret = "do-not-expose-this-key"
    session = Session({"organic_results": []})
    if case == "quota":
        session.status = 429
    elif case == "api_error":
        session.payload = {"error": secret}
    elif case == "network":
        session.error = requests.ConnectionError(f"https://serpapi.com/?api_key={secret}")
    else:
        session.payload = {"organic_results": "invalid"}
    budget = Budget()
    with pytest.raises(ProviderError) as error:
        SerpApiSearch(Settings(secret, secret), budget, session).search("x", "x", "")
    assert secret not in str(error.value)
    assert budget.searches == 1


def test_request_limits_prevent_network_calls():
    session = Session({})
    with pytest.raises(LimitReached):
        SerpApiSearch(Settings("test-key", "test-key"), Budget(max_searches=0), session).search(
            "x", "x", ""
        )
    assert not session.calls


def sdk_extractor(budget, handler):
    client = OpenAI(
        api_key="fake-not-a-real-key",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return OpenAIExtractor(Settings("test", "test"), budget, client)


def test_real_openai_sdk_request_with_mock_http_transport(live_case):
    result, payload = live_case
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert request.url.host == "api.openai.com"
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["max_completion_tokens"] == 3000
        return httpx.Response(
            200,
            json={
                "id": "mock",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(payload)},
                    }
                ],
                "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
            },
        )

    budget = Budget()
    extracted = sdk_extractor(budget, handler).extract(
        result.brand, result.context, result.sources, result.researched_at
    )
    assert extracted == payload
    assert budget.ai_calls == 1
    assert budget.tokens == 300
    assert len(seen) == 1


def test_openai_errors_no_hidden_retries_or_secret_leaks(live_case):
    result, _ = live_case
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            429, json={"error": {"message": "fake-not-a-real-key", "type": "rate_limit"}}
        )

    budget = Budget()
    with pytest.raises(ProviderError) as error:
        sdk_extractor(budget, handler).extract(
            result.brand, "", result.sources, result.researched_at
        )
    assert "fake-not-a-real-key" not in str(error.value)
    assert len(calls) == 1
    assert budget.ai_calls == 1 and budget.tokens > 3000


@pytest.mark.parametrize("token_cap,call_cap", [(1, 5), (100_000, 0)])
def test_openai_caps_block_requests_before_sending(live_case, token_cap, call_cap):
    result, _ = live_case
    calls = []
    with pytest.raises(LimitReached):
        sdk_extractor(
            Budget(max_tokens=token_cap, max_ai_calls=call_cap),
            lambda request: calls.append(request),
        ).extract(result.brand, "", result.sources, result.researched_at)
    assert calls == []


def test_settings_precedence_and_repr_hide_secrets(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "environment-serp-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    settings = load_settings({"SERPAPI_API_KEY": "ignored", "OPENAI_API_KEY": "secret-ai-key"})
    assert settings.serpapi_key == "environment-serp-key"
    assert settings.openai_key == "secret-ai-key"
    assert settings.ready
    assert "secret-ai-key" not in repr(settings)
    assert "environment-serp-key" not in repr(settings)


def test_source_priority_and_lookalike_domains():
    assert source_rank("https://auroratea.example/history", "Aurora Tea", "")[0] == 1
    assert source_rank("https://bloomberg.com/profile", "Aurora Tea", "")[0] == 2
    assert source_rank("https://pitchbook.com/profile", "Aurora Tea", "")[0] == 3
    assert source_rank("https://sec.gov/Archives/a", "Aurora Tea", "")[0] == 4
    assert source_rank("https://reuters.com/business/a", "Aurora Tea", "")[0] == 5
    assert source_rank("https://en.wikipedia.org/wiki/a", "Aurora Tea", "")[0] == 6
    assert source_rank("https://bloomberg.com.attacker.example/a", "Aurora Tea", "")[0] == 7
