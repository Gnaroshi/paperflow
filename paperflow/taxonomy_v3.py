from __future__ import annotations

import re
from collections.abc import Iterable


ROOT_COLLECTION_V3 = "AI Library"
REVIEW_QUEUE_COLLECTION = "AI Library/05 Review Queue"

COLLECTION_TREE_V3: list[str] = [
    REVIEW_QUEUE_COLLECTION,
    "AI Library/10 Active Reading",
    "AI Library/20 Areas/LLM/Reasoning & Planning",
    "AI Library/20 Areas/LLM/RAG & Retrieval",
    "AI Library/20 Areas/LLM/Agents & Tool Use",
    "AI Library/20 Areas/LLM/Code Intelligence",
    "AI Library/20 Areas/LLM/Alignment, Safety & Hallucination",
    "AI Library/20 Areas/Vision-Language/CLIP & Contrastive VLM",
    "AI Library/20 Areas/Vision-Language/Prompt Learning",
    "AI Library/20 Areas/Vision-Language/Document & Chart Understanding",
    "AI Library/20 Areas/Vision-Language/Medical VLM",
    "AI Library/20 Areas/Embodied AI/Robot Manipulation",
    "AI Library/20 Areas/Embodied AI/World Models",
    "AI Library/20 Areas/Embodied AI/VLA & Imitation Learning",
    "AI Library/20 Areas/Computer Vision/Object Detection",
    "AI Library/20 Areas/Computer Vision/Segmentation",
    "AI Library/20 Areas/Computer Vision/Anomaly & Defect Detection",
    "AI Library/20 Areas/Computer Vision/Industrial Inspection",
    "AI Library/20 Areas/Medical AI/Radiology & X-ray",
    "AI Library/20 Areas/Medical AI/Biomedical Imaging",
    "AI Library/20 Areas/Battery ML/SOH & RUL Prognostics",
    "AI Library/20 Areas/Battery ML/Degradation & Cycle Life",
    "AI Library/20 Areas/Representation/Self-Supervised Learning",
    "AI Library/20 Areas/Representation/Contrastive Learning",
    "AI Library/20 Areas/Representation/Metric Learning",
    "AI Library/20 Areas/Graph Learning/GNNs",
    "AI Library/20 Areas/Graph Learning/Knowledge Graphs",
    "AI Library/20 Areas/Time-Series/Forecasting",
    "AI Library/20 Areas/Time-Series/Dynamical Systems",
    "AI Library/20 Areas/Efficient ML/Inference & KV Cache",
    "AI Library/20 Areas/Efficient ML/Compression & Distillation",
    "AI Library/20 Areas/Efficient ML/MoE & Scaling",
    "AI Library/20 Areas/Scientific Discovery/Materials & Chemistry",
    "AI Library/20 Areas/Scientific Discovery/Bioinformatics",
    "AI Library/30 Resources/Surveys & Tutorials",
    "AI Library/30 Resources/Datasets & Benchmarks",
    "AI Library/30 Resources/Tools, Systems & Implementations",
    "AI Library/30 Resources/Foundational Papers",
    "AI Library/40 Cleanup/Possible Existing in Zotero",
    "AI Library/40 Cleanup/Update Candidates",
    "AI Library/40 Cleanup/Missing Metadata",
    "AI Library/40 Cleanup/Missing Abstract",
    "AI Library/90 Archives",
]

TAG_VOCABULARY_V3: list[str] = [
    "status/to-read",
    "status/skimmed",
    "status/read",
    "status/implemented",
    "status/cited",
    "area/llm-reasoning",
    "area/rag",
    "area/agents",
    "area/code-intelligence",
    "area/alignment-safety",
    "area/vlm-contrastive",
    "area/vlm-prompt-learning",
    "area/document-understanding",
    "area/medical-vlm",
    "area/robot-manipulation",
    "area/world-models",
    "area/vla-robotics",
    "area/object-detection",
    "area/segmentation",
    "area/anomaly-detection",
    "area/industrial-inspection",
    "area/medical-ai",
    "area/battery-ml",
    "area/representation-learning",
    "area/graph-learning",
    "area/time-series",
    "area/dynamical-systems",
    "area/efficient-ml",
    "area/scientific-discovery",
    "type/survey",
    "type/method",
    "type/benchmark",
    "type/dataset",
    "type/system",
    "type/theory",
    "type/foundational",
    "type/tutorial",
    "method/retrieval",
    "method/rag",
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
    "method/looped-transformer",
    "method/recurrent-depth",
    "method/adaptive-computation",
    "method/efficient-compute",
    "method/control",
    "method/evaluation",
    "method/alignment",
    "task/question-answering",
    "task/reasoning",
    "task/planning",
    "task/code-generation",
    "task/object-detection",
    "task/segmentation",
    "task/anomaly-detection",
    "task/robot-manipulation",
    "task/battery-prognostics",
    "task/rul-prediction",
    "task/medical-diagnosis",
    "task/multimodal-understanding",
    "cleanup/possible-existing",
    "cleanup/update-candidate",
    "cleanup/missing-metadata",
    "cleanup/missing-abstract",
    "paperflow/source-local-import",
    "source/arxiv",
    "source/conference",
    "source/journal",
    "source/workshop",
    "source/web",
    "source/unknown",
]

TAG_SET_V3 = set(TAG_VOCABULARY_V3)
STATUS_TAGS_V3 = {tag for tag in TAG_SET_V3 if tag.startswith("status/")}
DEFAULT_STATUS_TAG_V3 = "status/to-read"


def normalize_title_v3(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower()
    value = re.sub(r"\b(arxiv|preprint|pdf)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output


def clamp_tags_v3(tags: Iterable[str], minimum: int = 3, maximum: int = 10) -> list[str]:
    cleaned = [tag for tag in unique_preserve_order(tags) if tag in TAG_SET_V3]
    status = next((tag for tag in cleaned if tag in STATUS_TAGS_V3), DEFAULT_STATUS_TAG_V3)
    output = [status, *[tag for tag in cleaned if tag not in STATUS_TAGS_V3]]
    for fallback in ("type/method", "source/unknown"):
        if len(output) >= minimum:
            break
        if fallback not in output:
            output.append(fallback)
    return output[:maximum]


def area_slug_from_collection(path: str | None) -> str:
    if not path or path == REVIEW_QUEUE_COLLECTION:
        return "Review"
    parts = path.split("/")
    if len(parts) < 4:
        return "Review"
    slug = " - ".join(parts[2:])
    slug = re.sub(r"[^A-Za-z0-9 &+_.-]+", " ", slug)
    slug = re.sub(r"\s+", " ", slug).strip()
    return slug or "Review"
