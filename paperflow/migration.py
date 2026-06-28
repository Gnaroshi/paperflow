from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

from paperflow.classifier_v2 import classify_migration_item
from paperflow.metadata import enrich_items
from paperflow.migration_models import (
    DedupePlan,
    EnrichedZoteroItem,
    MigrationPlan,
    MigrationStats,
)
from paperflow.models import ZoteroItem
from paperflow.taxonomy_v2 import (
    COLLECTION_TREE_V2,
    DUPLICATE_COLLECTION,
    MISSING_ABSTRACT_COLLECTION,
    MISSING_METADATA_COLLECTION,
    NON_PAPER_COLLECTION,
    TAG_VOCABULARY_V2,
)
from paperflow.utils import ensure_parent_dir, read_json_model, read_jsonl_model, write_json


def load_enriched_or_raw(path: Path) -> list[EnrichedZoteroItem]:
    try:
        items = read_jsonl_model(path, EnrichedZoteroItem)
        if any(item.title and not item.normalized_title for item in items):
            return enrich_items(items)
        return items
    except ValueError:
        return enrich_items(read_jsonl_model(path, ZoteroItem))


def duplicate_maps(plan: DedupePlan | None) -> tuple[set[str], dict[str, str]]:
    if plan is None:
        return set(), {}
    candidates: set[str] = set()
    canonical_by_candidate: dict[str, str] = {}
    for group in plan.groups:
        for item in group.items:
            if not item.is_canonical:
                candidates.add(item.item_key)
                canonical_by_candidate[item.item_key] = group.canonical_item_key
    return candidates, canonical_by_candidate


def build_migration_plan(
    items: list[EnrichedZoteroItem],
    source_jsonl: str,
    dedupe_plan: DedupePlan | None = None,
    dedupe_plan_path: str | None = None,
) -> MigrationPlan:
    duplicate_keys, canonical_by_duplicate = duplicate_maps(dedupe_plan)
    migration_items = [
        classify_migration_item(
            item,
            duplicate_candidate=item.key in duplicate_keys,
            canonical_item_key=canonical_by_duplicate.get(item.key),
        )
        for item in items
    ]
    stats = MigrationStats(
        source_items=len(items),
        planned_items=len(migration_items),
        duplicate_candidates=sum(
            1 for item in migration_items if DUPLICATE_COLLECTION in item.target_collections
        ),
        missing_metadata=sum(
            1 for item in migration_items if MISSING_METADATA_COLLECTION in item.target_collections
        ),
        missing_abstract=sum(
            1 for item in migration_items if MISSING_ABSTRACT_COLLECTION in item.target_collections
        ),
        non_paper_items=sum(
            1 for item in migration_items if NON_PAPER_COLLECTION in item.target_collections
        ),
    )
    return MigrationPlan(
        source_jsonl=source_jsonl,
        dedupe_plan=dedupe_plan_path,
        collection_tree=list(COLLECTION_TREE_V2),
        tag_vocabulary=list(TAG_VOCABULARY_V2),
        stats=stats,
        items=migration_items,
    )


def write_migration_reports(
    plan: MigrationPlan,
    markdown_path: Path,
    csv_path: Path,
) -> None:
    collection_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    for item in plan.items:
        collection_counts.update(item.target_collections)
        tag_counts.update(item.normalized_tags)

    lines = [
        "# migration report",
        "",
        f"- Source items: {plan.stats.source_items}",
        f"- Planned items: {plan.stats.planned_items}",
        f"- Duplicate candidates: {plan.stats.duplicate_candidates}",
        f"- Missing metadata: {plan.stats.missing_metadata}",
        f"- Missing abstracts: {plan.stats.missing_abstract}",
        f"- Non-paper items: {plan.stats.non_paper_items}",
        "",
        "## Collection distribution",
        "",
    ]
    lines.extend(f"- {collection}: {count}" for collection, count in collection_counts.most_common())
    lines.extend(["", "## Tag distribution", ""])
    lines.extend(f"- {tag}: {count}" for tag, count in tag_counts.most_common())
    lines.extend(["", "## Low confidence items", ""])
    low_confidence = [item for item in plan.items if item.confidence < 0.55]
    if low_confidence:
        lines.extend(
            f"- {item.item_key} | {item.confidence:.2f} | {item.title or '(untitled)'}"
            for item in low_confidence
        )
    else:
        lines.append("- None")

    ensure_parent_dir(markdown_path)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    rows = [
        {
            "item_key": item.item_key,
            "title": item.title,
            "confidence": item.confidence,
            "target_collections": "; ".join(item.target_collections),
            "normalized_tags": "; ".join(item.normalized_tags),
            "duplicate_role": item.duplicate_role,
            "canonical_item_key": item.canonical_item_key,
            "metadata_issues": "; ".join(item.metadata_issues),
            "doi_normalized": item.doi_normalized,
            "arxiv_id": item.arxiv_id,
        }
        for item in plan.items
    ]
    ensure_parent_dir(csv_path)
    pd.DataFrame(rows).to_csv(csv_path, index=False)


def plan_migration_file(
    input_path: Path,
    output_path: Path,
    markdown_path: Path,
    csv_path: Path,
    dedupe_path: Path | None = None,
) -> MigrationPlan:
    items = load_enriched_or_raw(input_path)
    dedupe_plan = None
    dedupe_plan_path = None
    if dedupe_path and dedupe_path.exists():
        dedupe_plan = read_json_model(dedupe_path, DedupePlan)
        dedupe_plan_path = str(dedupe_path)
    plan = build_migration_plan(
        items=items,
        source_jsonl=str(input_path),
        dedupe_plan=dedupe_plan,
        dedupe_plan_path=dedupe_plan_path,
    )
    write_json(output_path, plan)
    write_migration_reports(plan, markdown_path, csv_path)
    return plan


def default_items_input(enriched_path: Path, raw_path: Path) -> Path:
    return enriched_path if enriched_path.exists() else raw_path


def default_dedupe_input(enriched_path: Path, raw_path: Path) -> Path:
    return enriched_path if enriched_path.exists() else raw_path
