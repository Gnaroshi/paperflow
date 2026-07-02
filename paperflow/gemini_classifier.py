from __future__ import annotations

import json
from typing import Any

from paperflow.credentials import GeminiClient
from paperflow.taxonomy_v3 import (
    AMBIGUOUS_CLASSIFICATION_COLLECTION,
    COLLECTION_TREE_V3,
    TAG_SET_V3,
    clamp_tags_v3,
    unique_preserve_order,
)


CLASSIFICATION_PROMPT_TEMPLATE = """\
You are classifying academic AI/ML papers for a Zotero library.
You must choose only from the allowed collection tree and tag vocabulary.
Use evidence from title, abstract, first pages, DOI, arXiv categories, and venue.
Do not invent metadata.
Do not classify as RAG unless retrieval is central.
Return strict JSON.

Allowed collection tree:
{collections_json}

Allowed tag vocabulary:
{tags_json}

Return this JSON schema exactly:
{{
  "primary_collection": "...",
  "secondary_collections": [],
  "tags": [],
  "confidence": 0.0,
  "evidence": [
    {{
      "source": "title|abstract|pdf_page|arxiv|doi",
      "quote": "short evidence text"
    }}
  ],
  "rationale": "...",
  "needs_review": false
}}

Paper evidence:
Title: {title}
DOI: {doi}
arXiv ID: {arxiv_id}
arXiv categories: {arxiv_categories}
Venue: {venue}
Abstract:
{abstract}

First pages:
{first_pages}
"""


def _gemini_text(raw: dict[str, Any]) -> str:
    return str(raw["candidates"][0]["content"]["parts"][0]["text"])


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        cleaned = cleaned.removesuffix("```").strip()
    return json.loads(cleaned)


def build_gemini_classification_prompt(evidence: dict[str, Any]) -> str:
    return CLASSIFICATION_PROMPT_TEMPLATE.format(
        collections_json=json.dumps(COLLECTION_TREE_V3, ensure_ascii=False, indent=2),
        tags_json=json.dumps(sorted(TAG_SET_V3), ensure_ascii=False, indent=2),
        title=evidence.get("title") or "",
        doi=(evidence.get("detected") or {}).get("doi") or "",
        arxiv_id=(evidence.get("detected") or {}).get("arxiv_id") or "",
        arxiv_categories=evidence.get("arxiv_categories") or "",
        venue=evidence.get("venue") or "",
        abstract=(evidence.get("abstract") or "")[:5000],
        first_pages=(evidence.get("first_pages_text") or "")[:12000],
    )


def review_fallback(reason: str, *, error_type: str | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error_type": error_type or "gemini_classification_rejected",
        "classification": {
            "target_collections": [AMBIGUOUS_CLASSIFICATION_COLLECTION],
            "normalized_tags": clamp_tags_v3(["status/review-needed", "cleanup/low-confidence", "source/local-pdf", "type/method"]),
            "confidence": 0.25,
            "rationale": reason,
            "evidence_snippets": [],
            "gemini_used": False,
            "gemini_rejected": True,
            "gemini_rejection_reason": reason,
        },
    }


def validate_gemini_classification_payload(
    payload: dict[str, Any],
    *,
    review_threshold: float,
) -> dict[str, Any]:
    primary = payload.get("primary_collection")
    secondaries = payload.get("secondary_collections") or []
    tags = payload.get("tags") or []
    confidence = float(payload.get("confidence") or 0.0)
    if primary not in COLLECTION_TREE_V3:
        return review_fallback(f"Gemini returned unknown primary collection: {primary}")
    invalid_collections = [collection for collection in secondaries if collection not in COLLECTION_TREE_V3]
    if invalid_collections:
        return review_fallback(f"Gemini returned unknown secondary collections: {invalid_collections}")
    invalid_tags = [tag for tag in tags if tag not in TAG_SET_V3]
    if invalid_tags:
        return review_fallback(f"Gemini returned unknown tags: {invalid_tags}")
    if confidence < review_threshold or payload.get("needs_review"):
        return review_fallback(
            f"Gemini confidence {confidence:.2f} below review threshold {review_threshold:.2f}"
        )

    target_collections = unique_preserve_order([primary, *secondaries])[:3]
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
    return {
        "ok": True,
        "classification": {
            "target_collections": target_collections,
            "normalized_tags": clamp_tags_v3(["status/to-read", *tags]),
            "confidence": min(1.0, max(0.0, confidence)),
            "rationale": f"Gemini fallback: {payload.get('rationale') or 'classified from supplied evidence'}",
            "evidence_snippets": evidence,
            "gemini_used": True,
            "gemini_rejected": False,
        },
    }


def classify_with_gemini(
    evidence: dict[str, Any],
    gemini: GeminiClient,
    *,
    review_threshold: float = 0.75,
) -> dict[str, Any]:
    result = gemini.generate(build_gemini_classification_prompt(evidence))
    if not result.get("ok"):
        return review_fallback(
            result.get("message") or "Gemini classification request failed",
            error_type=result.get("error_type") or "request_failed",
        )
    try:
        payload = _parse_json_object(_gemini_text(result.get("raw") or {}))
    except Exception:
        return review_fallback("Gemini returned invalid JSON", error_type="invalid_gemini_json")
    return validate_gemini_classification_payload(payload, review_threshold=review_threshold)
