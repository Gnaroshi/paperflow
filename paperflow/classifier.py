from __future__ import annotations

import math
import re
from collections import Counter

from paperflow.models import PlanItem, ZoteroItem
from paperflow.taxonomy import INBOX_COLLECTION, clamp_tags, normalize_tags


LOW_CONFIDENCE_THRESHOLD = 0.55


COLLECTION_RULES: dict[str, tuple[tuple[str, float], ...]] = {
    "AI Library/20 Areas/LLM": (
        ("large language model", 2.5),
        ("language model", 2.0),
        ("llm", 2.0),
        ("gpt", 1.5),
        ("llama", 1.5),
        ("transformer", 1.2),
        ("instruction tuning", 1.5),
    ),
    "AI Library/20 Areas/RAG": (
        ("retrieval augmented generation", 3.0),
        ("retrieval-augmented generation", 3.0),
        ("rag", 2.5),
        ("retriever", 1.4),
        ("dense retrieval", 1.6),
        ("vector database", 1.3),
        ("knowledge retrieval", 1.3),
    ),
    "AI Library/20 Areas/Agents": (
        ("agent", 1.7),
        ("agents", 1.7),
        ("tool use", 1.5),
        ("autonomous", 1.2),
        ("multi-agent", 2.0),
        ("planning", 1.0),
        ("workflow", 1.0),
    ),
    "AI Library/20 Areas/Multimodal": (
        ("multimodal", 2.5),
        ("vision-language", 2.2),
        ("vision language", 2.2),
        ("image", 0.9),
        ("video", 1.0),
        ("audio", 1.0),
        ("clip", 1.5),
        ("vlm", 2.0),
    ),
    "AI Library/20 Areas/Evaluation": (
        ("evaluation", 1.8),
        ("evaluate", 1.2),
        ("benchmark", 2.0),
        ("metric", 1.4),
        ("leaderboard", 1.4),
        ("hallucination", 1.2),
        ("judge", 1.0),
    ),
    "AI Library/20 Areas/Efficient ML": (
        ("efficient", 1.4),
        ("efficiency", 1.4),
        ("quantization", 2.0),
        ("pruning", 1.8),
        ("distillation", 1.8),
        ("compression", 1.5),
        ("moe", 1.6),
        ("mixture of experts", 2.0),
        ("lora", 1.5),
        ("latency", 1.2),
    ),
    "AI Library/20 Areas/Alignment & Safety": (
        ("alignment", 1.8),
        ("safety", 1.8),
        ("rlhf", 2.0),
        ("dpo", 2.0),
        ("preference", 1.2),
        ("harmless", 1.4),
        ("red team", 1.4),
        ("jailbreak", 1.5),
        ("bias", 1.0),
    ),
    "AI Library/20 Areas/Code Intelligence": (
        ("code generation", 2.4),
        ("program synthesis", 2.0),
        ("software engineering", 1.8),
        ("repository", 1.0),
        ("bug", 1.0),
        ("code llm", 2.0),
        ("unit test", 1.0),
    ),
    "AI Library/20 Areas/Scientific Discovery": (
        ("scientific discovery", 2.5),
        ("chemistry", 1.4),
        ("biology", 1.4),
        ("protein", 1.4),
        ("materials", 1.4),
        ("drug discovery", 1.8),
        ("laboratory", 1.0),
    ),
    "AI Library/20 Areas/Theory": (
        ("theory", 1.8),
        ("theorem", 1.6),
        ("proof", 1.2),
        ("generalization bound", 1.7),
        ("scaling law", 1.6),
        ("optimization", 1.0),
    ),
    "AI Library/30 Resources/Surveys": (
        ("survey", 3.0),
        ("review", 2.0),
        ("taxonomy", 2.0),
        ("overview", 1.5),
    ),
    "AI Library/30 Resources/Datasets & Benchmarks": (
        ("dataset", 2.2),
        ("corpus", 1.8),
        ("benchmark", 2.2),
        ("leaderboard", 1.6),
    ),
    "AI Library/30 Resources/Tools & Systems": (
        ("system", 1.8),
        ("tool", 1.6),
        ("framework", 1.6),
        ("platform", 1.4),
        ("library", 1.2),
        ("infrastructure", 1.2),
    ),
    "AI Library/30 Resources/Implementations": (
        ("implementation", 2.0),
        ("reproducibility", 1.8),
        ("replication", 1.5),
        ("codebase", 1.2),
    ),
    "AI Library/30 Resources/Reading Lists": (
        ("reading list", 3.0),
        ("syllabus", 2.0),
        ("curriculum", 1.8),
    ),
}


TAG_RULES: dict[str, tuple[str, ...]] = {
    "type/survey": ("survey", "review", "taxonomy", "overview"),
    "type/benchmark": ("benchmark", "leaderboard", "evaluation suite"),
    "type/dataset": ("dataset", "corpus", "data set"),
    "type/system": ("system", "tool", "framework", "platform", "library"),
    "type/theory": ("theory", "theorem", "proof", "bound"),
    "method/rag": ("rag", "retrieval augmented generation", "retrieval-augmented generation"),
    "method/agent": ("agent", "agents", "tool use", "multi-agent"),
    "method/rlhf": ("rlhf", "reinforcement learning from human feedback"),
    "method/dpo": ("dpo", "direct preference optimization"),
    "method/moe": ("moe", "mixture of experts"),
    "method/retrieval": ("retrieval", "retriever", "dense retrieval"),
    "method/distillation": ("distillation", "distilled"),
    "method/finetuning": ("fine-tuning", "finetuning", "fine tuning", "lora"),
    "method/prompting": ("prompt", "prompting", "in-context"),
    "method/evaluation": ("evaluation", "evaluate", "metric", "judge"),
    "method/alignment": ("alignment", "preference", "safety", "harmless"),
    "task/code-generation": ("code generation", "program synthesis", "software engineering"),
    "task/question-answering": ("question answering", "question-answering", "qa"),
    "task/reasoning": ("reasoning", "chain-of-thought", "chain of thought"),
    "task/planning": ("planning", "plan generation"),
    "task/document-understanding": ("document understanding", "document ai", "pdf"),
    "task/information-extraction": ("information extraction", "entity extraction"),
    "task/scientific-discovery": ("scientific discovery", "drug discovery", "protein"),
    "task/multimodal-understanding": ("multimodal", "vision-language", "image", "video"),
}

CONFERENCE_VENUES = (
    "neurips",
    "icml",
    "iclr",
    "acl",
    "emnlp",
    "naacl",
    "cvpr",
    "iccv",
    "eccv",
    "aaai",
    "ijcai",
    "kdd",
    "sigir",
)


def _contains_phrase(text: str, phrase: str) -> bool:
    if len(phrase) <= 4 or not phrase.replace("-", "").isalnum():
        return phrase in text
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def build_signal_text(item: ZoteroItem, pdf_snippet: str | None = None) -> str:
    parts = [
        item.title or "",
        item.abstract_note or "",
        item.doi or "",
        item.url or "",
        item.publication_title or "",
        " ".join(item.existing_tags),
        pdf_snippet or "",
    ]
    return " ".join(parts).lower()


def score_collections(text: str) -> Counter[str]:
    scores: Counter[str] = Counter()
    for collection, rules in COLLECTION_RULES.items():
        for phrase, weight in rules:
            if _contains_phrase(text, phrase):
                scores[collection] += weight
    return scores


def confidence_from_scores(scores: Counter[str]) -> float:
    if not scores:
        return 0.2
    top_score = scores.most_common(1)[0][1]
    second_score = scores.most_common(2)[1][1] if len(scores) > 1 else 0
    confidence = 0.32 + 0.12 * top_score + 0.03 * math.sqrt(second_score)
    return round(min(0.95, confidence), 2)


def choose_collections(scores: Counter[str], confidence: float) -> list[str]:
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        return [INBOX_COLLECTION]
    selected = [
        collection
        for collection, score in scores.most_common()
        if score >= 1.4
    ][:3]
    return selected or [INBOX_COLLECTION]


def infer_source_tag(item: ZoteroItem, text: str) -> str:
    venue = (item.publication_title or "").lower()
    if "arxiv" in text or "10.48550" in text:
        return "source/arxiv"
    if "workshop" in venue:
        return "source/workshop"
    if any(venue_name in venue for venue_name in CONFERENCE_VENUES):
        return "source/conference"
    if "journal" in venue or item.item_type == "journalArticle":
        return "source/journal"
    return "source/preprint"


def infer_tags(item: ZoteroItem, text: str) -> list[str]:
    tags = normalize_tags(item.existing_tags)

    for tag, phrases in TAG_RULES.items():
        if any(_contains_phrase(text, phrase) for phrase in phrases):
            tags.append(tag)

    if not any(tag.startswith("type/") for tag in tags):
        tags.append("type/method")

    if not any(tag.startswith("source/") for tag in tags):
        tags.append(infer_source_tag(item, text))

    return clamp_tags(tags)


def classify_item(item: ZoteroItem, pdf_snippet: str | None = None) -> PlanItem:
    text = build_signal_text(item, pdf_snippet)
    scores = score_collections(text)
    confidence = confidence_from_scores(scores)
    target_collections = choose_collections(scores, confidence)
    normalized_tags = infer_tags(item, text)

    if target_collections == [INBOX_COLLECTION]:
        rationale = "Low-confidence or ambiguous metadata; sent to Inbox."
    else:
        rationale = "Matched deterministic metadata keywords for planned collections."

    return PlanItem(
        item_key=item.key,
        version=item.version,
        title=item.title,
        doi=item.doi,
        url=item.url,
        year=item.year,
        abstract_present=bool(item.abstract_note),
        publication_title=item.publication_title,
        target_collections=target_collections,
        normalized_tags=normalized_tags,
        confidence=confidence,
        rationale=rationale,
    )
