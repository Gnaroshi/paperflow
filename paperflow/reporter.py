from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from paperflow.models import OrganizePlan, PlanItem
from paperflow.taxonomy import INBOX_COLLECTION, title_fingerprint
from paperflow.utils import ensure_parent_dir, read_json_model


def _has_arxiv_id(item: PlanItem) -> bool:
    text = " ".join([item.doi or "", item.url or "", item.title or ""]).lower()
    return "arxiv" in text or "10.48550" in text


def duplicate_title_groups(items: list[PlanItem]) -> dict[str, list[PlanItem]]:
    groups: dict[str, list[PlanItem]] = defaultdict(list)
    for item in items:
        fingerprint = title_fingerprint(item.title)
        if fingerprint:
            groups[fingerprint].append(item)
    return {title: group for title, group in groups.items() if len(group) > 1}


def build_report(plan: OrganizePlan) -> tuple[str, pd.DataFrame]:
    collection_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    for item in plan.items:
        collection_counts.update(item.target_collections)
        tag_counts.update(item.normalized_tags)

    low_confidence = [item for item in plan.items if item.confidence < 0.55]
    no_doi_or_arxiv = [
        item for item in plan.items if not item.doi and not _has_arxiv_id(item)
    ]
    no_abstract = [item for item in plan.items if not item.abstract_present]
    duplicate_groups = duplicate_title_groups(plan.items)

    lines = [
        "# paperflow organize report",
        "",
        "## Summary",
        "",
        f"- Scanned items: {plan.stats.scanned_items}",
        f"- Classified items: {plan.stats.classified_items}",
        f"- Sent to Inbox: {plan.stats.inbox_items}",
        f"- Low-confidence items: {plan.stats.low_confidence_items}",
        "",
        "## Collection distribution",
        "",
    ]
    for collection, count in collection_counts.most_common():
        lines.append(f"- {collection}: {count}")

    lines.extend(["", "## Tag distribution", ""])
    for tag, count in tag_counts.most_common():
        lines.append(f"- {tag}: {count}")

    lines.extend(["", "## Low-confidence items", ""])
    if low_confidence:
        for item in low_confidence:
            lines.append(
                f"- {item.item_key} | {item.confidence:.2f} | {item.title or '(untitled)'}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Duplicate-looking titles", ""])
    if duplicate_groups:
        for group in duplicate_groups.values():
            rendered = ", ".join(item.item_key for item in group)
            title = group[0].title or "(untitled)"
            lines.append(f"- {title}: {rendered}")
    else:
        lines.append("- None")

    lines.extend(["", "## Items without DOI/arXiv ID", ""])
    if no_doi_or_arxiv:
        for item in no_doi_or_arxiv:
            lines.append(f"- {item.item_key} | {item.title or '(untitled)'}")
    else:
        lines.append("- None")

    lines.extend(["", "## Items without abstracts", ""])
    if no_abstract:
        for item in no_abstract:
            lines.append(f"- {item.item_key} | {item.title or '(untitled)'}")
    else:
        lines.append("- None")

    rows = []
    for item in plan.items:
        rows.append(
            {
                "item_key": item.item_key,
                "title": item.title,
                "confidence": item.confidence,
                "inbox": item.target_collections == [INBOX_COLLECTION],
                "target_collections": "; ".join(item.target_collections),
                "normalized_tags": "; ".join(item.normalized_tags),
                "doi": item.doi,
                "url": item.url,
                "year": item.year,
                "abstract_present": item.abstract_present,
            }
        )
    return "\n".join(lines) + "\n", pd.DataFrame(rows)


def write_report(plan_path: Path, markdown_path: Path, csv_path: Path) -> OrganizePlan:
    plan = read_json_model(plan_path, OrganizePlan)
    markdown, dataframe = build_report(plan)
    ensure_parent_dir(markdown_path)
    markdown_path.write_text(markdown, encoding="utf-8")
    ensure_parent_dir(csv_path)
    dataframe.to_csv(csv_path, index=False)
    return plan
