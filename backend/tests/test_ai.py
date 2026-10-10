import json

import httpx
import pytest
from conftest import analyse, sample

from app import ai
from app.config import Settings
from app.errors import AppError


@pytest.fixture(scope="module")
def result():
    return analyse(sample("retail_product_performance.csv"), "retail.csv")


def enabled(monkeypatch) -> Settings:
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    return Settings()


def transport_returning(text: str, status: int = 200, seen: list | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json={"content": [{"type": "text", "text": text}]})

    return httpx.MockTransport(handler)


def test_disabled_by_default(result):
    with pytest.raises(AppError) as e:
        ai.explain(result.profile, result.findings, Settings())
    assert e.value.code == "ai_not_configured" and e.value.status == 503


def test_context_contains_no_raw_rows(result):
    ctx = json.dumps(ai.build_context(result.profile, result.findings))
    assert "item 17" not in ctx  # product_name values are never sent
    assert "P017" not in ctx
    assert '"F1"' in ctx


def test_valid_response_is_validated_and_numbers_checked(monkeypatch, result):
    s = enabled(monkeypatch)
    f1 = result.findings.findings[0]
    reply = {
        "summary": "Revenue is concentrated in one category.",
        "explanations": [
            {"finding_id": f1.id, "explanation": f"{f1.title}. This is supported by the evidence."},
            {"finding_id": "F99", "explanation": "Made-up finding."},
            {"finding_id": f1.id, "explanation": "Sales grew by 73.2% which is invented."},
        ],
        "follow_ups": [{"question": "Check pricing by region", "finding_ids": [f1.id, "F42"]}],
    }
    seen: list = []
    out = ai.explain(result.profile, result.findings, s, transport=transport_returning("Here:\n" + json.dumps(reply), seen=seen))
    assert [e.finding_id for e in out.explanations] == [f1.id, f1.id]  # unknown F99 dropped
    assert out.explanations[0].unverified_numbers == []
    assert out.explanations[1].unverified_numbers == ["73.2"]
    assert out.follow_ups[0].finding_ids == [f1.id]
    assert any("F99" in w for w in out.warnings)
    # The key is sent only as a header to the API, never in the body
    req = seen[0]
    assert req.headers["x-api-key"] == "test-key-not-real"
    assert "test-key-not-real" not in req.content.decode()


@pytest.mark.parametrize("text", ["not json at all", '{"summary": 1}', "{broken"])
def test_malformed_response_rejected(monkeypatch, result, text):
    with pytest.raises(AppError) as e:
        ai.explain(result.profile, result.findings, enabled(monkeypatch), transport=transport_returning(text))
    assert e.value.code == "ai_invalid_response"


def test_upstream_error_does_not_leak_details(monkeypatch, result):
    with pytest.raises(AppError) as e:
        ai.explain(
            result.profile,
            result.findings,
            enabled(monkeypatch),
            transport=transport_returning("secret upstream body", status=401),
        )
    assert e.value.code == "ai_error" and "secret" not in e.value.message


def test_network_failure(monkeypatch, result):
    def boom(request):
        raise httpx.ConnectError("down")

    with pytest.raises(AppError) as e:
        ai.explain(result.profile, result.findings, enabled(monkeypatch), transport=httpx.MockTransport(boom))
    assert e.value.code == "ai_unavailable"
