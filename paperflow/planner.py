from __future__ import annotations

from pathlib import Path

from paperflow.classifier import LOW_CONFIDENCE_THRESHOLD, classify_item
from paperflow.models import OrganizePlan, PlanStats, ZoteroItem
from paperflow.pdf_text import extract_pdf_snippet
from paperflow.taxonomy import COLLECTION_TREE, INBOX_COLLECTION, TAG_VOCABULARY
from paperflow.utils import read_jsonl_model, write_json


def _snippet_for_item(item: ZoteroItem, use_pdf_snippets: bool) -> str:
    if not use_pdf_snippets:
        return ""
    for attachment in item.attachments:
        if attachment.is_pdf and attachment.local_path:
            snippet = extract_pdf_snippet(attachment.local_path)
            if snippet:
                return snippet
    return ""


def build_plan(
    items: list[ZoteroItem],
    source_jsonl: str,
    use_pdf_snippets: bool = False,
) -> OrganizePlan:
    plan_items = [
        classify_item(item, _snippet_for_item(item, use_pdf_snippets))
        for item in items
    ]
    inbox_items = sum(
        1 for item in plan_items if item.target_collections == [INBOX_COLLECTION]
    )
    low_confidence_items = sum(
        1 for item in plan_items if item.confidence < LOW_CONFIDENCE_THRESHOLD
    )
    stats = PlanStats(
        scanned_items=len(items),
        classified_items=len(items) - inbox_items,
        inbox_items=inbox_items,
        low_confidence_items=low_confidence_items,
    )
    return OrganizePlan(
        source_jsonl=source_jsonl,
        collection_tree=list(COLLECTION_TREE),
        tag_vocabulary=list(TAG_VOCABULARY),
        stats=stats,
        items=plan_items,
    )


def plan_from_jsonl(
    input_path: Path,
    output_path: Path,
    use_pdf_snippets: bool = False,
) -> OrganizePlan:
    items = read_jsonl_model(input_path, ZoteroItem)
    plan = build_plan(
        items=items,
        source_jsonl=str(input_path),
        use_pdf_snippets=use_pdf_snippets,
    )
    write_json(output_path, plan)
    return plan
