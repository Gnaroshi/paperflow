from __future__ import annotations

import math
import re
from collections import Counter

from paperflow.metadata import is_arxiv_doi, is_arxiv_url
from paperflow.migration_models import EnrichedZoteroItem, MigrationItem
from paperflow.taxonomy_v2 import (
    DUPLICATE_COLLECTION,
    INBOX_COLLECTION_V2,
    MISSING_ABSTRACT_COLLECTION,
    MISSING_METADATA_COLLECTION,
    NON_PAPER_COLLECTION,
    clamp_tags_v2,
    unique_preserve_order,
)


AREA_COLLECTION_TAGS = {
    "AI Library/20 Areas/LLM & Reasoning": "area/llm-reasoning",
    "AI Library/20 Areas/Vision-Language Models": "area/vlm",
    "AI Library/20 Areas/Vision-Language-Action & Robotics": "area/vla-robotics",
    "AI Library/20 Areas/World Models & Embodied AI": "area/world-models",
    "AI Library/20 Areas/Anomaly & Defect Detection": "area/anomaly-detection",
    "AI Library/20 Areas/Battery ML & Prognostics": "area/battery-ml",
    "AI Library/20 Areas/Medical AI & Biomedical VLM": "area/medical-ai",
    "AI Library/20 Areas/Classic CV & Detection": "area/classic-cv",
    "AI Library/20 Areas/Representation Learning": "area/representation-learning",
    "AI Library/20 Areas/Graph Learning": "area/graph-learning",
    "AI Library/20 Areas/Time-Series & Dynamical Systems": "area/time-series",
    "AI Library/20 Areas/Efficient ML": "area/efficient-ml",
    "AI Library/20 Areas/Alignment & Safety": "area/alignment-safety",
    "AI Library/20 Areas/RAG": "area/rag",
}

FOUNDATIONAL_TITLES = {
    "attention is all you need",
    "deep residual learning for image recognition",
    "imagenet classification with deep convolutional neural networks",
    "batch normalization accelerating deep network training by reducing internal covariate shift",
    "an image is worth 16x16 words transformers for image recognition at scale",
    "learning transferable visual models from natural language supervision",
    "you only look once unified real time object detection",
    "faster r cnn towards real time object detection with region proposal networks",
    "u net convolutional networks for biomedical image segmentation",
}

COLLECTION_RULES_V2: dict[str, tuple[tuple[str, float], ...]] = {
    "AI Library/20 Areas/LLM & Reasoning": (
        ("large language model", 2.5),
        ("llm", 2.2),
        ("chain of thought", 2.0),
        ("chain-of-thought", 2.0),
        ("reasoning", 1.5),
        ("question answering", 1.2),
        ("prompting", 1.0),
    ),
    "AI Library/20 Areas/Vision-Language Models": (
        ("vision-language", 2.5),
        ("vision language", 2.5),
        ("vlm", 2.3),
        ("clip", 1.8),
        ("multimodal", 1.5),
        ("visual question answering", 1.4),
        ("prompt learning", 1.2),
    ),
    "AI Library/20 Areas/Vision-Language-Action & Robotics": (
        ("vision-language-action", 3.0),
        ("vision language action", 3.0),
        ("vla", 2.4),
        ("robot manipulation", 2.4),
        ("robotic manipulation", 2.4),
        ("imitation learning", 1.8),
        ("policy learning", 1.8),
        ("world model", 1.5),
        ("manipulation policy", 2.0),
    ),
    "AI Library/20 Areas/World Models & Embodied AI": (
        ("world model", 3.0),
        ("world models", 3.0),
        ("looped world model", 3.2),
        ("looped transformer", 2.8),
        ("recurrent depth", 2.5),
        ("adaptive computation", 2.2),
        ("embodied ai", 2.0),
        ("model-based control", 1.8),
    ),
    "AI Library/20 Areas/Anomaly & Defect Detection": (
        ("anomaly detection", 2.5),
        ("defect detection", 2.4),
        ("mvtec", 2.0),
        ("industrial inspection", 2.0),
        ("surface defect", 1.8),
        ("visual inspection", 1.5),
    ),
    "AI Library/20 Areas/Battery ML & Prognostics": (
        ("battery degradation", 2.6),
        ("battery life", 2.2),
        ("cycle life", 2.0),
        ("state of health", 2.0),
        ("soh", 1.8),
        ("remaining useful life", 2.0),
        ("rul", 1.8),
        ("thermal runaway", 1.8),
        ("battery prognostics", 2.3),
    ),
    "AI Library/20 Areas/Medical AI & Biomedical VLM": (
        ("chest x-ray", 2.2),
        ("chest xray", 2.2),
        ("radiology", 2.0),
        ("biomedical", 1.8),
        ("medical diagnosis", 1.8),
        ("clinical", 1.4),
        ("pathology", 1.4),
    ),
    "AI Library/20 Areas/Classic CV & Detection": (
        ("resnet", 2.0),
        ("yolo", 2.0),
        ("faster r-cnn", 2.1),
        ("faster r cnn", 2.1),
        ("detr", 1.8),
        ("efficientnet", 1.8),
        ("grad-cam", 1.8),
        ("fpn", 1.5),
        ("object detection", 2.0),
        ("segmentation", 1.5),
        ("vit", 1.5),
    ),
    "AI Library/20 Areas/Representation Learning": (
        ("representation learning", 2.5),
        ("contrastive learning", 2.0),
        ("self-supervised", 1.8),
        ("semi-supervised", 1.6),
        ("embedding", 1.2),
        ("metric learning", 1.5),
    ),
    "AI Library/20 Areas/Graph Learning": (
        ("graph neural network", 2.5),
        ("gnn", 2.2),
        ("gcn", 2.0),
        ("graph convolution", 2.0),
        ("graph embedding", 1.8),
        ("knowledge graph", 1.8),
    ),
    "AI Library/20 Areas/Time-Series & Dynamical Systems": (
        ("time series", 2.0),
        ("timeseries", 2.0),
        ("neural ode", 2.2),
        ("controlled differential", 2.0),
        ("temporal dynamics", 1.8),
        ("dynamical system", 1.8),
        ("model predictive control", 2.0),
    ),
    "AI Library/20 Areas/Efficient ML": (
        ("kv cache", 2.2),
        ("cache compression", 2.0),
        ("efficient inference", 2.0),
        ("efficient compute", 2.0),
        ("adaptive computation", 1.8),
        ("model scaling", 1.6),
        ("quantization", 2.0),
        ("distillation", 1.7),
        ("pruning", 1.7),
        ("efficient architecture", 1.7),
    ),
    "AI Library/20 Areas/Alignment & Safety": (
        ("jailbreak", 2.2),
        ("hallucination", 1.8),
        ("alignment", 1.8),
        ("llm safety", 2.0),
        ("safety", 1.5),
        ("preference optimization", 1.8),
        ("red team", 1.8),
    ),
    "AI Library/30 Resources/Surveys": (
        ("survey", 3.0),
        ("review", 2.0),
        ("taxonomy", 2.0),
        ("overview", 1.5),
    ),
    "AI Library/30 Resources/Datasets & Benchmarks": (
        ("dataset", 2.2),
        ("benchmark", 2.2),
        ("leaderboard", 1.6),
        ("corpus", 1.6),
    ),
    "AI Library/30 Resources/Tools & Systems": (
        ("toolkit", 2.0),
        ("system", 1.8),
        ("framework", 1.7),
        ("platform", 1.5),
        ("library", 1.3),
    ),
    "AI Library/30 Resources/Implementations": (
        ("implementation", 2.0),
        ("reproduction", 1.8),
        ("reproducibility", 1.8),
        ("codebase", 1.5),
    ),
}

RAG_TERMS = (
    "retrieval augmented generation",
    "retrieval-augmented generation",
    "rag",
    "retriever",
    "document retrieval",
    "passage retrieval",
    "dense retrieval",
    "indexing",
    "knowledge-base retrieval",
    "knowledge base retrieval",
    "citation-grounded generation",
    "query-document retrieval",
    "query document retrieval",
    "retrieval system",
    "retrieval model",
)

TAG_RULES_V2: dict[str, tuple[str, ...]] = {
    "type/survey": ("survey", "review", "taxonomy", "overview"),
    "type/benchmark": ("benchmark", "leaderboard"),
    "type/dataset": ("dataset", "corpus"),
    "type/system": ("system", "framework", "platform", "toolkit"),
    "type/theory": ("theory", "theorem", "proof", "bound"),
    "method/prompting": ("prompt", "prompting", "prompt learning"),
    "method/finetuning": ("fine tuning", "fine-tuning", "finetuning", "lora"),
    "method/distillation": ("distillation", "distilled"),
    "method/contrastive-learning": ("contrastive learning",),
    "method/self-supervised-learning": ("self-supervised", "self supervised"),
    "method/semi-supervised-learning": ("semi-supervised", "semi supervised"),
    "method/transformer": ("transformer", "attention is all you need", "vit"),
    "method/cnn": ("cnn", "convolutional", "resnet", "alexnet"),
    "method/gnn": ("gnn", "gcn", "graph neural network"),
    "method/diffusion": ("diffusion", "score-based"),
    "method/world-model": ("world model",),
    "method/looped-transformer": ("looped transformer", "looped world model"),
    "method/recurrent-depth": ("recurrent depth",),
    "method/adaptive-computation": ("adaptive computation",),
    "method/efficient-compute": ("efficient compute", "efficient computation", "adaptive computation"),
    "method/control": ("control", "model predictive control"),
    "method/retrieval": ("retriever", "document retrieval", "passage retrieval", "dense retrieval"),
    "method/evaluation": ("evaluation", "metric", "judge"),
    "method/alignment": ("alignment", "safety", "preference optimization"),
    "task/question-answering": ("question answering", "qa", "visual question answering"),
    "task/reasoning": ("reasoning", "chain of thought", "chain-of-thought"),
    "task/planning": ("planning", "planner"),
    "task/object-detection": ("object detection", "yolo", "faster r-cnn", "detr"),
    "task/segmentation": ("segmentation", "u-net", "unet"),
    "task/anomaly-detection": ("anomaly detection", "defect detection"),
    "task/robot-manipulation": ("robot manipulation", "robotic manipulation", "manipulation policy"),
    "task/battery-prognostics": ("battery prognostics", "battery degradation", "battery life"),
    "task/rul-prediction": ("remaining useful life", "rul"),
    "task/medical-diagnosis": ("medical diagnosis", "radiology", "chest x-ray"),
    "task/multimodal-understanding": ("multimodal", "vision-language", "vision language"),
}

CONFERENCE_VENUES = (
    "neurips",
    "nips",
    "icml",
    "iclr",
    "cvpr",
    "iccv",
    "eccv",
    "aaai",
    "ijcai",
    "acl",
    "emnlp",
    "naacl",
    "kdd",
    "sigir",
    "iros",
    "icra",
)


def contains_phrase(text: str, phrase: str) -> bool:
    phrase = phrase.lower()
    if len(phrase) <= 4:
        return re.search(rf"\b{re.escape(phrase)}\b", text) is not None
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def signal_text(item: EnrichedZoteroItem) -> str:
    parts = [
        item.title or "",
        item.abstract_note or "",
        item.doi or "",
        item.doi_normalized or "",
        item.arxiv_id or "",
        item.url or "",
        item.extra or "",
        item.publication_title or "",
        " ".join(item.existing_tags),
        " ".join(
            " ".join([attachment.filename or "", attachment.title or ""])
            for attachment in item.attachments
        ),
    ]
    return " ".join(parts).lower()


def is_rag(text: str) -> bool:
    return any(contains_phrase(text, term) for term in RAG_TERMS)


def is_foundational(item: EnrichedZoteroItem, text: str) -> bool:
    if item.normalized_title in FOUNDATIONAL_TITLES:
        return True
    return any(contains_phrase(text, title) for title in FOUNDATIONAL_TITLES)


def is_non_paper(item: EnrichedZoteroItem, text: str) -> bool:
    if item.item_type in {"webpage", "webPage", "blogPost", "forumPost"}:
        return True
    return any(
        contains_phrase(text, phrase)
        for phrase in ("tutorial", "reading list", "syllabus", "course notes", "documentation")
    )


def score_collections_v2(item: EnrichedZoteroItem, text: str) -> Counter[str]:
    scores: Counter[str] = Counter()
    if is_rag(text):
        scores["AI Library/20 Areas/RAG"] += 3.0
    for collection, rules in COLLECTION_RULES_V2.items():
        for phrase, weight in rules:
            if contains_phrase(text, phrase):
                scores[collection] += weight
    if is_foundational(item, text):
        scores["AI Library/30 Resources/Foundational Papers"] += 3.0
    return scores


def confidence(scores: Counter[str]) -> float:
    if not scores:
        return 0.3
    top = scores.most_common(1)[0][1]
    second = scores.most_common(2)[1][1] if len(scores) > 1 else 0
    return round(min(0.96, 0.36 + top * 0.11 + math.sqrt(second) * 0.03), 2)


def source_tag(item: EnrichedZoteroItem, text: str) -> str:
    venue = (item.publication_title or "").lower()
    if item.arxiv_id and (
        is_arxiv_doi(item.doi_normalized)
        or is_arxiv_doi(item.doi)
        or is_arxiv_url(item.url)
    ):
        return "source/arxiv"
    if item.item_type == "preprint" and is_arxiv_url(item.url):
        return "source/arxiv"
    if "workshop" in venue:
        return "source/workshop"
    if any(venue_name in venue for venue_name in CONFERENCE_VENUES):
        return "source/conference"
    if item.item_type == "conferencePaper" or "conference" in venue:
        return "source/conference"
    if "journal" in venue or item.item_type == "journalArticle":
        return "source/journal"
    if item.item_type in {"webpage", "webPage", "blogPost"} or (item.url and not item.doi_normalized):
        return "source/web"
    return "source/unknown"


def infer_tags_v2(
    item: EnrichedZoteroItem,
    text: str,
    collections: list[str],
    duplicate_candidate: bool,
) -> list[str]:
    tags: list[str] = ["status/to-read"]
    tags.extend(AREA_COLLECTION_TAGS[collection] for collection in collections if collection in AREA_COLLECTION_TAGS)

    if is_foundational(item, text):
        tags.append("type/foundational")
    if is_non_paper(item, text):
        tags.extend(["type/non-paper", "cleanup/non-paper"])

    for tag, phrases in TAG_RULES_V2.items():
        if any(contains_phrase(text, phrase) for phrase in phrases):
            tags.append(tag)

    if duplicate_candidate:
        tags.append("cleanup/duplicate-candidate")
    if "missing-doi-or-arxiv" in item.metadata_issues:
        tags.append("cleanup/missing-metadata")
    if "missing-abstract" in item.metadata_issues:
        tags.append("cleanup/missing-abstract")

    if not any(tag.startswith("type/") for tag in tags):
        tags.append("type/method")
    tags.append(source_tag(item, text))
    return clamp_tags_v2(tags)


def choose_primary_collections(
    item: EnrichedZoteroItem,
    scores: Counter[str],
    text: str,
) -> list[str]:
    if is_non_paper(item, text):
        return [NON_PAPER_COLLECTION]
    selected = [
        collection
        for collection, score in scores.most_common()
        if score >= 1.5
    ]
    if not selected:
        return [INBOX_COLLECTION_V2]
    return selected[:3]


def classify_migration_item(
    item: EnrichedZoteroItem,
    duplicate_candidate: bool = False,
    canonical_item_key: str | None = None,
) -> MigrationItem:
    text = signal_text(item)
    scores = score_collections_v2(item, text)
    primary = choose_primary_collections(item, scores, text)

    required_cleanup: list[str] = []
    if duplicate_candidate:
        required_cleanup.append(DUPLICATE_COLLECTION)
    if "missing-doi-or-arxiv" in item.metadata_issues:
        required_cleanup.append(MISSING_METADATA_COLLECTION)
    if "missing-abstract" in item.metadata_issues:
        required_cleanup.append(MISSING_ABSTRACT_COLLECTION)

    target_collections = unique_preserve_order([*required_cleanup, *primary])[:3]
    if not target_collections:
        target_collections = [INBOX_COLLECTION_V2]

    normalized_tags = infer_tags_v2(item, text, target_collections, duplicate_candidate)
    duplicate_role = "duplicate_candidate" if duplicate_candidate else None
    reason_parts = []
    if duplicate_candidate:
        reason_parts.append("duplicate candidate from dedupe plan")
    if required_cleanup:
        reason_parts.append("metadata cleanup rules applied")
    if primary != [INBOX_COLLECTION_V2]:
        reason_parts.append("taxonomy v2 keyword rules matched")
    if not reason_parts:
        reason_parts.append("ambiguous item assigned to Inbox")

    return MigrationItem(
        item_key=item.key,
        version=item.version,
        title=item.title,
        normalized_title=item.normalized_title,
        item_type=item.item_type,
        year=item.year,
        doi=item.doi,
        doi_normalized=item.doi_normalized,
        arxiv_id=item.arxiv_id,
        url=item.url,
        abstract_present=bool(item.abstract_note),
        publication_title=item.publication_title,
        existing_collection_keys=item.existing_collection_keys,
        existing_tags=item.existing_tags,
        target_collections=target_collections,
        normalized_tags=normalized_tags,
        duplicate_role=duplicate_role,
        canonical_item_key=canonical_item_key,
        metadata_quality_score=item.metadata_quality_score,
        metadata_issues=item.metadata_issues,
        confidence=confidence(scores),
        rationale="; ".join(reason_parts),
    )
