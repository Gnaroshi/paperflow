from paperflow.models import OrganizePlan, ZoteroItem
from paperflow.planner import build_plan
from paperflow.taxonomy import INBOX_COLLECTION, STATUS_TAGS, TAG_SET


def test_plan_json_schema_validation() -> None:
    items = [
        ZoteroItem(
            key="AGENT1",
            version=12,
            item_type="conferencePaper",
            title="Tool-Using Agents for Planning",
            abstract_note="Autonomous agents use tools and planning with language models.",
            publication_title="NeurIPS",
        ),
        ZoteroItem(
            key="UNKNOWN1",
            item_type="journalArticle",
            title="Notes from a Reading Group",
        ),
    ]

    plan = build_plan(items, source_jsonl="data/zotero_items.jsonl")
    validated = OrganizePlan.model_validate_json(plan.model_dump_json())

    assert validated.stats.scanned_items == 2
    assert validated.stats.inbox_items == 1
    assert validated.items[1].target_collections == [INBOX_COLLECTION]
    for item in validated.items:
        assert 1 <= len(item.target_collections) <= 3
        assert 3 <= len(item.normalized_tags) <= 10
        assert set(item.normalized_tags) <= TAG_SET
        assert sum(tag in STATUS_TAGS for tag in item.normalized_tags) == 1
