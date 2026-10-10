"""Optional AI explanation layer.

Safeguards:

* Off by default. Requires AI_ENABLED=true AND an ANTHROPIC_API_KEY on the
  backend. The key never reaches the browser.
* The user must explicitly consent per request (the UI explains what is sent).
* Only summaries are sent: column names and types, row counts, and the
  findings with their evidence. Raw rows are never sent.
* The model must answer in a fixed JSON structure that references finding IDs.
  The response is validated; explanations that cite unknown IDs are dropped,
  and numbers that do not appear in the supplied evidence are flagged.
* AI output is displayed as clearly labelled commentary. It never changes a
  calculation and is never executed.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings
from .errors import AppError
from .schemas import AIExplanation, AIFindingExplanation, AIFollowUp, DatasetProfile, FindingsResult

API_URL = "https://api.anthropic.com/v1/messages"
DISCLAIMER = (
    "This commentary was written by an AI model from the calculated findings only. It may be wrong; "
    "rely on the findings and evidence above, which were calculated deterministically."
)

SYSTEM_PROMPT = """You explain data-analysis findings to a non-technical business reader.
Rules you must follow:
- Use ONLY the numbers and facts in the JSON you are given. Do not invent metrics, percentages or totals.
- Every explanation must refer to a finding by its id (e.g. "F1"). Only use ids that appear in the input.
- Describe associations, never causes. Say "is associated with", not "causes" or "drives".
- Do not claim to have seen the raw data; you only have summaries.
- Reply with JSON only, no prose before or after, in exactly this shape:
{"summary": "<2-4 sentence plain-English overview>",
 "explanations": [{"finding_id": "F1", "explanation": "<1-3 sentences>"}],
 "follow_ups": [{"question": "<a useful next analysis>", "finding_ids": ["F1"]}]}"""


class _RawExplanation(BaseModel):
    finding_id: str
    explanation: str


class _RawFollowUp(BaseModel):
    question: str
    finding_ids: list[str] = []


class _RawResponse(BaseModel):
    summary: str
    explanations: list[_RawExplanation]
    follow_ups: list[_RawFollowUp] = []


_NUM_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")


def build_context(profile: DatasetProfile, findings: FindingsResult) -> dict[str, Any]:
    """The ONLY data sent to the model: no raw rows."""
    return {
        "dataset": {
            "rows": profile.rows,
            "columns": [
                {"name": c.name, "type": c.inferred_type, "role": c.role, "missing_pct": c.missing_pct}
                for c in profile.column_profiles
            ],
            "duplicate_rows": profile.duplicate_rows,
        },
        "findings": [
            {
                "id": f.id,
                "title": f.title,
                "description": f.description,
                "evidence": [e.model_dump() for e in f.evidence],
                "columns": f.columns,
                "period": f.period,
                "caveat": f.caveat,
            }
            for f in findings.findings[:10]
        ],
    }


def _numbers(text: str) -> set[float]:
    out = set()
    for m in _NUM_RE.findall(text):
        cleaned = m.replace(",", "").rstrip(".")
        try:
            out.add(round(abs(float(cleaned)), 6))
        except ValueError:
            continue
    return out


def _is_known(n: float, known: set[float]) -> bool:
    if n in known or n < 10 and float(n).is_integer():  # small counts like "two groups" / "3 findings"
        return True
    return any(abs(n - k) <= max(0.01, 0.005 * abs(k)) or round(k) == n or round(k, 1) == n for k in known)


def parse_response(text: str, context: dict[str, Any], model: str) -> AIExplanation:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise AppError(502, "ai_invalid_response", "The AI service returned a response that was not in the expected format.")
    try:
        raw = _RawResponse.model_validate(json.loads(text[start : end + 1]))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AppError(
            502, "ai_invalid_response", "The AI service returned a response that was not in the expected format."
        ) from exc

    valid_ids = {f["id"] for f in context["findings"]}
    known_numbers = _numbers(json.dumps(context))
    warnings: list[str] = []
    explanations: list[AIFindingExplanation] = []
    for e in raw.explanations:
        if e.finding_id not in valid_ids:
            warnings.append(f"An explanation referencing unknown finding '{e.finding_id}' was removed.")
            continue
        unverified = sorted(
            {m for m in _NUM_RE.findall(e.explanation) if not _is_known(next(iter(_numbers(m)), 0.0), known_numbers)}
        )
        if unverified:
            warnings.append(
                f"The explanation for {e.finding_id} contains numbers not present in the evidence: {', '.join(unverified)}."
            )
        explanations.append(
            AIFindingExplanation(finding_id=e.finding_id, explanation=e.explanation.strip(), unverified_numbers=unverified)
        )
    follow_ups = [
        AIFollowUp(question=f.question.strip(), finding_ids=[i for i in f.finding_ids if i in valid_ids])
        for f in raw.follow_ups[:5]
    ]
    summary_unverified = sorted(
        {m for m in _NUM_RE.findall(raw.summary) if not _is_known(next(iter(_numbers(m)), 0.0), known_numbers)}
    )
    if summary_unverified:
        warnings.append(f"The summary contains numbers not present in the evidence: {', '.join(summary_unverified)}.")
    return AIExplanation(
        summary=raw.summary.strip(),
        explanations=explanations,
        follow_ups=follow_ups,
        model=model,
        warnings=warnings,
        disclaimer=DISCLAIMER,
    )


def explain(
    profile: DatasetProfile,
    findings: FindingsResult,
    settings: Settings,
    transport: httpx.BaseTransport | None = None,
) -> AIExplanation:
    if not settings.ai_available:
        raise AppError(
            503, "ai_not_configured", "AI explanations are not enabled on this server. All analysis features work without it."
        )
    if not findings.findings:
        raise AppError(422, "no_findings", "There are no findings to explain.")
    context = build_context(profile, findings)
    payload = {
        "model": settings.ai_model,
        "max_tokens": 1500,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": "Explain these findings:\n" + json.dumps(context)}],
    }
    headers = {
        "x-api-key": settings.anthropic_api_key or "",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    try:
        with httpx.Client(timeout=settings.ai_timeout_seconds, transport=transport) as client:
            response = client.post(API_URL, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise AppError(502, "ai_unavailable", "The AI service could not be reached. Your analysis is unaffected.") from exc
    if response.status_code != 200:
        # Never echo the key or the full upstream body.
        raise AppError(
            502, "ai_error", f"The AI service returned an error (HTTP {response.status_code}). Your analysis is unaffected."
        )
    try:
        body = response.json()
        text = "".join(block.get("text", "") for block in body.get("content", []) if block.get("type") == "text")
    except (ValueError, AttributeError) as exc:
        raise AppError(502, "ai_invalid_response", "The AI service returned an unreadable response.") from exc
    return parse_response(text, context, settings.ai_model)
