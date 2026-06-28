from paperflow.classifier import classify_item
from paperflow.models import ZoteroItem
from paperflow.taxonomy import INBOX_COLLECTION, STATUS_TAGS, TAG_SET, normalize_tag


def test_classifier_assigns_rag_collection_and_tags() -> None:
    item = ZoteroItem(
        key="RAG123",
        item_type="journalArticle",
        title="Retrieval-Augmented Generation for Large Language Models",
        abstract_note=(
            "We study retrieval-augmented generation for question answering "
            "with large language models."
        ),
        url="https://arxiv.org/abs/2401.00001",
        publication_title="arXiv",
    )

    plan_item = classify_item(item)

    assert "AI Library/20 Areas/RAG" in plan_item.target_collections
    assert plan_item.confidence >= 0.55
    assert "method/rag" in plan_item.normalized_tags
    assert "task/question-answering" in plan_item.normalized_tags
    assert "source/arxiv" in plan_item.normalized_tags
    assert sum(tag in STATUS_TAGS for tag in plan_item.normalized_tags) == 1
    assert set(plan_item.normalized_tags) <= TAG_SET


def test_tag_normalizer_maps_common_aliases() -> None:
    assert normalize_tag("Fine Tuning") == "method/finetuning"
    assert normalize_tag("QA") == "task/question-answering"
    assert normalize_tag("to read") == "status/to-read"
    assert normalize_tag("not-in-vocabulary") is None


def test_low_confidence_falls_back_to_inbox() -> None:
    item = ZoteroItem(
        key="UNK123",
        item_type="journalArticle",
        title="A Short Note on Unclear Topics",
    )

    plan_item = classify_item(item)

    assert plan_item.confidence < 0.55
    assert plan_item.target_collections == [INBOX_COLLECTION]
    assert 3 <= len(plan_item.normalized_tags) <= 10
