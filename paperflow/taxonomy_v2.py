from __future__ import annotations

import re
from collections.abc import Iterable


ROOT_COLLECTION = "AI Library"

COLLECTION_TREE_V2: list[str] = [
    "AI Library/00 Inbox",
    "AI Library/10 Active Reading",
    "AI Library/20 Areas/LLM & Reasoning",
    "AI Library/20 Areas/Vision-Language Models",
    "AI Library/20 Areas/Vision-Language-Action & Robotics",
    "AI Library/20 Areas/Anomaly & Defect Detection",
    "AI Library/20 Areas/Battery ML & Prognostics",
    "AI Library/20 Areas/Medical AI & Biomedical VLM",
    "AI Library/20 Areas/Classic CV & Detection",
    "AI Library/20 Areas/Representation Learning",
    "AI Library/20 Areas/Graph Learning",
    "AI Library/20 Areas/Time-Series & Dynamical Systems",
    "AI Library/20 Areas/Efficient ML",
    "AI Library/20 Areas/Alignment & Safety",
    "AI Library/20 Areas/RAG",
    "AI Library/30 Resources/Surveys",
    "AI Library/30 Resources/Datasets & Benchmarks",
    "AI Library/30 Resources/Tools & Systems",
    "AI Library/30 Resources/Implementations",
    "AI Library/30 Resources/Foundational Papers",
    "AI Library/40 Cleanup/Duplicate Candidates",
    "AI Library/40 Cleanup/Missing Metadata",
    "AI Library/40 Cleanup/Missing Abstract",
    "AI Library/40 Cleanup/Non-Paper Items",
    "AI Library/90 Archives",
]

INBOX_COLLECTION_V2 = "AI Library/00 Inbox"
DUPLICATE_COLLECTION = "AI Library/40 Cleanup/Duplicate Candidates"
MISSING_METADATA_COLLECTION = "AI Library/40 Cleanup/Missing Metadata"
MISSING_ABSTRACT_COLLECTION = "AI Library/40 Cleanup/Missing Abstract"
NON_PAPER_COLLECTION = "AI Library/40 Cleanup/Non-Paper Items"

TAG_VOCABULARY_V2: list[str] = [
    "status/to-read",
    "status/skimmed",
    "status/read",
    "status/implemented",
    "status/cited",
    "area/llm-reasoning",
    "area/vlm",
    "area/vla-robotics",
    "area/anomaly-detection",
    "area/battery-ml",
    "area/medical-ai",
    "area/classic-cv",
    "area/representation-learning",
    "area/graph-learning",
    "area/time-series",
    "area/efficient-ml",
    "area/alignment-safety",
    "area/rag",
    "type/survey",
    "type/method",
    "type/benchmark",
    "type/dataset",
    "type/system",
    "type/theory",
    "type/foundational",
    "type/tutorial",
    "type/non-paper",
    "method/prompting",
    "method/finetuning",
    "method/distillation",
    "method/contrastive-learning",
    "method/self-supervised-learning",
    "method/semi-supervised-learning",
    "method/transformer",
    "method/cnn",
    "method/gnn",
    "method/diffusion",
    "method/world-model",
    "method/control",
    "method/retrieval",
    "method/evaluation",
    "method/alignment",
    "task/question-answering",
    "task/reasoning",
    "task/planning",
    "task/object-detection",
    "task/segmentation",
    "task/anomaly-detection",
    "task/robot-manipulation",
    "task/battery-prognostics",
    "task/rul-prediction",
    "task/medical-diagnosis",
    "task/multimodal-understanding",
    "cleanup/duplicate-candidate",
    "cleanup/missing-metadata",
    "cleanup/missing-abstract",
    "cleanup/non-paper",
    "source/arxiv",
    "source/conference",
    "source/journal",
    "source/workshop",
    "source/web",
    "source/unknown",
]

TAG_SET_V2 = set(TAG_VOCABULARY_V2)
STATUS_TAGS_V2 = {tag for tag in TAG_SET_V2 if tag.startswith("status/")}
MANAGED_TAG_PREFIXES = (
    "status/",
    "area/",
    "type/",
    "method/",
    "task/",
    "source/",
    "cleanup/",
)
DEFAULT_STATUS_TAG = "status/to-read"


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower()
    value = re.sub(r"\b(arxiv|preprint)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"10\.\d{4,9}/[^\s\"'<>]+", value, flags=re.IGNORECASE)
    doi = match.group(0) if match else value
    doi = doi.strip().rstrip(".,;").lower()
    return doi or None


def collection_path_parts(path: str) -> list[str]:
    return [part for part in path.split("/") if part]


def expand_collection_paths(paths: Iterable[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for path in paths:
        parts = collection_path_parts(path)
        for idx in range(1, len(parts) + 1):
            partial = "/".join(parts[:idx])
            if partial not in seen:
                expanded.append(partial)
                seen.add(partial)
    return expanded


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output


def clamp_tags_v2(tags: Iterable[str], minimum: int = 3, maximum: int = 10) -> list[str]:
    cleaned = [tag for tag in unique_preserve_order(tags) if tag in TAG_SET_V2]
    non_status = [tag for tag in cleaned if tag not in STATUS_TAGS_V2]
    status = next((tag for tag in cleaned if tag in STATUS_TAGS_V2), DEFAULT_STATUS_TAG)
    output = [status, *non_status]
    for fallback in ("type/method", "source/unknown"):
        if len(output) >= minimum:
            break
        if fallback not in output:
            output.append(fallback)
    return output[:maximum]


def managed_tag(tag: str) -> bool:
    return tag.startswith(MANAGED_TAG_PREFIXES)
