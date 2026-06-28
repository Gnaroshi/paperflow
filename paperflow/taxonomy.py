from __future__ import annotations

import re
from collections.abc import Iterable


ROOT_COLLECTION = "AI Library"

COLLECTION_TREE: list[str] = [
    "AI Library/00 Inbox",
    "AI Library/20 Areas/LLM",
    "AI Library/20 Areas/RAG",
    "AI Library/20 Areas/Agents",
    "AI Library/20 Areas/Multimodal",
    "AI Library/20 Areas/Evaluation",
    "AI Library/20 Areas/Efficient ML",
    "AI Library/20 Areas/Alignment & Safety",
    "AI Library/20 Areas/Code Intelligence",
    "AI Library/20 Areas/Scientific Discovery",
    "AI Library/20 Areas/Theory",
    "AI Library/30 Resources/Surveys",
    "AI Library/30 Resources/Datasets & Benchmarks",
    "AI Library/30 Resources/Tools & Systems",
    "AI Library/30 Resources/Implementations",
    "AI Library/30 Resources/Reading Lists",
    "AI Library/90 Archives",
]

INBOX_COLLECTION = "AI Library/00 Inbox"

TAG_VOCABULARY: list[str] = [
    "status/to-read",
    "status/skimmed",
    "status/read",
    "status/implemented",
    "status/cited",
    "type/survey",
    "type/method",
    "type/benchmark",
    "type/dataset",
    "type/system",
    "type/theory",
    "method/rag",
    "method/agent",
    "method/rlhf",
    "method/dpo",
    "method/moe",
    "method/retrieval",
    "method/distillation",
    "method/finetuning",
    "method/prompting",
    "method/evaluation",
    "method/alignment",
    "task/code-generation",
    "task/question-answering",
    "task/reasoning",
    "task/planning",
    "task/document-understanding",
    "task/information-extraction",
    "task/scientific-discovery",
    "task/multimodal-understanding",
    "source/arxiv",
    "source/conference",
    "source/journal",
    "source/workshop",
    "source/preprint",
]

TAG_SET = set(TAG_VOCABULARY)
STATUS_TAGS = {tag for tag in TAG_VOCABULARY if tag.startswith("status/")}
DEFAULT_STATUS_TAG = "status/to-read"

TAG_ALIASES = {
    "to read": "status/to-read",
    "to-read": "status/to-read",
    "todo": "status/to-read",
    "skimmed": "status/skimmed",
    "read": "status/read",
    "implemented": "status/implemented",
    "cited": "status/cited",
    "survey": "type/survey",
    "review": "type/survey",
    "benchmark": "type/benchmark",
    "benchmarks": "type/benchmark",
    "dataset": "type/dataset",
    "datasets": "type/dataset",
    "system": "type/system",
    "systems": "type/system",
    "theory": "type/theory",
    "rag": "method/rag",
    "retrieval augmented generation": "method/rag",
    "retrieval-augmented generation": "method/rag",
    "agent": "method/agent",
    "agents": "method/agent",
    "rlhf": "method/rlhf",
    "dpo": "method/dpo",
    "moe": "method/moe",
    "retrieval": "method/retrieval",
    "distillation": "method/distillation",
    "fine tuning": "method/finetuning",
    "fine-tuning": "method/finetuning",
    "finetuning": "method/finetuning",
    "prompting": "method/prompting",
    "evaluation": "method/evaluation",
    "eval": "method/evaluation",
    "alignment": "method/alignment",
    "code generation": "task/code-generation",
    "code-generation": "task/code-generation",
    "qa": "task/question-answering",
    "question answering": "task/question-answering",
    "question-answering": "task/question-answering",
    "reasoning": "task/reasoning",
    "planning": "task/planning",
    "document understanding": "task/document-understanding",
    "information extraction": "task/information-extraction",
    "scientific discovery": "task/scientific-discovery",
    "multimodal": "task/multimodal-understanding",
    "arxiv": "source/arxiv",
    "conference": "source/conference",
    "journal": "source/journal",
    "workshop": "source/workshop",
    "preprint": "source/preprint",
}


def normalize_free_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.strip().lower())


def normalize_tag(tag: str) -> str | None:
    cleaned = normalize_free_text(tag)
    if not cleaned:
        return None
    if cleaned in TAG_ALIASES:
        return TAG_ALIASES[cleaned]

    normalized = cleaned.replace("_", "-")
    normalized = re.sub(r"\s*/\s*", "/", normalized)
    normalized = re.sub(r"\s+", "-", normalized)
    return normalized if normalized in TAG_SET else None


def normalize_tags(tags: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized_tag = normalize_tag(tag)
        if normalized_tag and normalized_tag not in seen:
            normalized.append(normalized_tag)
            seen.add(normalized_tag)
    return normalized


def ensure_exactly_one_status(
    tags: Iterable[str], default: str = DEFAULT_STATUS_TAG
) -> list[str]:
    output: list[str] = []
    existing_status: str | None = None
    for tag in tags:
        if tag in STATUS_TAGS:
            existing_status = existing_status or tag
            continue
        output.append(tag)

    status = existing_status or default
    return [status, *output]


def clamp_tags(tags: Iterable[str], minimum: int = 3, maximum: int = 10) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for tag in ensure_exactly_one_status(tags):
        if tag in TAG_SET and tag not in seen:
            output.append(tag)
            seen.add(tag)

    for fallback in ("type/method", "source/preprint"):
        if len(output) >= minimum:
            break
        if fallback not in seen:
            output.append(fallback)
            seen.add(fallback)

    return output[:maximum]


def collection_is_allowed(path: str) -> bool:
    return path in COLLECTION_TREE


def title_fingerprint(title: str | None) -> str:
    cleaned = normalize_free_text(title)
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()
