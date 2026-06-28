from paperflow.classifier_v2 import classify_migration_item
from paperflow.metadata import enrich_item
from paperflow.models import ZoteroItem


def _enriched(title: str, abstract: str, doi: str = "10.1000/example") -> object:
    return enrich_item(
        ZoteroItem(
            key=title[:6].upper().replace(" ", "X"),
            item_type="journalArticle",
            title=title,
            abstract_note=abstract,
            doi=doi,
        )
    )


def test_strict_rag_classification() -> None:
    item = _enriched(
        "Retrieval-Augmented Generation with Dense Retrieval",
        "A retriever indexes documents and grounds generation in passages.",
    )

    plan_item = classify_migration_item(item)

    assert "AI Library/20 Areas/RAG" in plan_item.target_collections
    assert "area/rag" in plan_item.normalized_tags


def test_battery_papers_do_not_become_rag() -> None:
    item = _enriched(
        "Battery Cycle Life Prediction with Representation Learning",
        "We predict battery degradation, state of health, and remaining useful life.",
    )

    plan_item = classify_migration_item(item)

    assert "AI Library/20 Areas/Battery ML & Prognostics" in plan_item.target_collections
    assert "AI Library/20 Areas/RAG" not in plan_item.target_collections


def test_robot_manipulation_goes_to_vla_robotics() -> None:
    item = _enriched(
        "Vision-Language-Action Models for Robot Manipulation",
        "A VLA policy learns imitation learning for robotic manipulation.",
    )

    plan_item = classify_migration_item(item)

    assert "AI Library/20 Areas/Vision-Language-Action & Robotics" in plan_item.target_collections
    assert "area/vla-robotics" in plan_item.normalized_tags


def test_classic_cv_foundational_papers_go_to_foundational_papers() -> None:
    item = _enriched(
        "Attention Is All You Need",
        "The Transformer architecture replaces recurrence with attention.",
    )

    plan_item = classify_migration_item(item)

    assert "AI Library/30 Resources/Foundational Papers" in plan_item.target_collections
    assert "type/foundational" in plan_item.normalized_tags
