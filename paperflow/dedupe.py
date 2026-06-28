from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from paperflow.metadata import enrich_items
from paperflow.migration_models import (
    DedupePlan,
    DuplicateGroup,
    DuplicateItem,
    EnrichedZoteroItem,
)
from paperflow.models import ReadingActivity, ZoteroItem
from paperflow.reading_activity import finalize_reading_activity
from paperflow.utils import read_jsonl_model, write_json
from paperflow.zotero_local import DEFAULT_LIBRARY_PREFIX, DEFAULT_LOCAL_API_BASE_URL, ZoteroLocalClient
from paperflow.zotero_web import ZoteroWebClient


def _has_pdf(item: ZoteroItem) -> bool:
    return any(attachment.is_pdf for attachment in item.attachments) or bool(
        item.reading_activity.pdf_attachment_count
    )


def _creator_count(item: ZoteroItem) -> int:
    return sum(1 for creator in item.creators if creator.name or creator.last_name)


def _title_is_not_broken(item: EnrichedZoteroItem) -> bool:
    title = (item.normalized_title or "").strip()
    if not title or title in {"untitled", "no title"}:
        return False
    return len(title) >= 5 and any(char.isalpha() for char in title)


def metadata_quality_points(item: EnrichedZoteroItem) -> int:
    score = 0
    if item.doi_normalized:
        score += 20
    if item.arxiv_id:
        score += 20
    if item.abstract_note:
        score += 15
    if item.year:
        score += 5
    if item.publication_title:
        score += 5
    if item.url:
        score += 5
    score += min(10, _creator_count(item) * 2)
    if _title_is_not_broken(item):
        score += 10
    if _has_pdf(item):
        score += 10
    return min(100, score)


def metadata_completeness_count(item: EnrichedZoteroItem) -> int:
    return sum(
        [
            bool(item.doi_normalized),
            bool(item.arxiv_id),
            bool(item.abstract_note),
            bool(item.year),
            bool(item.publication_title),
            bool(item.url),
            bool(_creator_count(item)),
            _title_is_not_broken(item),
            _has_pdf(item),
        ]
    )


def version_or_date_modified_score(item: EnrichedZoteroItem) -> int:
    if item.date_modified:
        try:
            normalized = item.date_modified.replace("Z", "+00:00")
            return int(datetime.fromisoformat(normalized).timestamp())
        except ValueError:
            pass
    return item.version or 0


def canonical_rank_tuple(item: EnrichedZoteroItem) -> tuple[bool, float, bool, int, int, int]:
    activity = finalize_reading_activity(item.reading_activity)
    return (
        activity.has_reading_work,
        activity.score,
        _has_pdf(item),
        metadata_quality_points(item),
        metadata_completeness_count(item),
        version_or_date_modified_score(item),
    )


def choose_canonical(items: list[EnrichedZoteroItem]) -> EnrichedZoteroItem:
    return max(items, key=canonical_rank_tuple)


def _reading_summary(activity: ReadingActivity) -> str:
    activity = finalize_reading_activity(activity)
    return ", ".join(activity.evidence) if activity.evidence else "no reading work"


def canonical_reason(
    canonical: EnrichedZoteroItem,
    items: list[EnrichedZoteroItem],
    suggested_metadata_source: EnrichedZoteroItem | None,
) -> str:
    activity = finalize_reading_activity(canonical.reading_activity)
    if activity.has_reading_work:
        reason = f"Selected because it preserves reading work: {_reading_summary(activity)}."
    elif _has_pdf(canonical):
        reason = "Selected because no duplicate has reading work and this item has a PDF attachment."
    else:
        reason = "Selected because no duplicate has reading work; metadata completeness was strongest."

    if suggested_metadata_source and suggested_metadata_source.key != canonical.key:
        reason += (
            f" {suggested_metadata_source.key} has better metadata, so metadata "
            "merge is suggested."
        )
    return reason


def _duplicate_item(item: EnrichedZoteroItem, canonical_key: str) -> DuplicateItem:
    activity = finalize_reading_activity(item.reading_activity)
    is_canonical = item.key == canonical_key
    return DuplicateItem(
        item_key=item.key,
        title=item.title,
        doi_normalized=item.doi_normalized,
        arxiv_id=item.arxiv_id,
        year=item.year,
        has_pdf_attachment=_has_pdf(item),
        metadata_quality_score=metadata_quality_points(item),
        reading_activity=activity,
        canonical_rank_tuple=list(canonical_rank_tuple(item)),
        is_canonical=is_canonical,
        unsafe_to_delete=activity.has_reading_work,
    )


def _make_group(
    idx: int,
    items: list[EnrichedZoteroItem],
    match_type: str,
) -> DuplicateGroup:
    canonical = choose_canonical(items)
    best_metadata_item = max(items, key=metadata_quality_points)
    metadata_merge_suggested = (
        best_metadata_item.key != canonical.key
        and metadata_quality_points(best_metadata_item) > metadata_quality_points(canonical)
    )
    return DuplicateGroup(
        group_id=f"dup-{idx:04d}",
        match_type=match_type,  # type: ignore[arg-type]
        normalized_title=canonical.normalized_title,
        canonical_item_key=canonical.key,
        canonical_reason=canonical_reason(
            canonical,
            items,
            best_metadata_item if metadata_merge_suggested else None,
        ),
        metadata_merge_suggested=metadata_merge_suggested,
        suggested_metadata_source_item_key=best_metadata_item.key
        if metadata_merge_suggested
        else None,
        items=[_duplicate_item(item, canonical.key) for item in items],
    )


def _groups_by_field(
    items: list[EnrichedZoteroItem], field_name: str
) -> list[list[EnrichedZoteroItem]]:
    grouped: dict[str, list[EnrichedZoteroItem]] = defaultdict(list)
    for item in items:
        value = getattr(item, field_name)
        if value:
            grouped[value].append(item)
    return [group for group in grouped.values() if len(group) > 1]


def detect_duplicate_groups(items: list[EnrichedZoteroItem]) -> list[DuplicateGroup]:
    groups: list[DuplicateGroup] = []
    grouped_keys: set[str] = set()

    for field_name, match_type in (
        ("doi_normalized", "strong_doi"),
        ("arxiv_id", "strong_arxiv"),
    ):
        for item_group in _groups_by_field(items, field_name):
            groups.append(_make_group(len(groups) + 1, item_group, match_type))
            grouped_keys.update(item.key for item in item_group)

    for item_group in _groups_by_field(items, "normalized_title"):
        if any(item.key in grouped_keys for item in item_group):
            continue
        groups.append(_make_group(len(groups) + 1, item_group, "likely_title"))
        grouped_keys.update(item.key for item in item_group)

    title_year_groups: dict[tuple[str, int | None], list[EnrichedZoteroItem]] = defaultdict(list)
    for item in items:
        if item.normalized_title:
            title_year_groups[(item.normalized_title, item.year)].append(item)
    for item_group in title_year_groups.values():
        if len(item_group) < 2 or any(item.key in grouped_keys for item in item_group):
            continue
        groups.append(_make_group(len(groups) + 1, item_group, "likely_title"))
        grouped_keys.update(item.key for item in item_group)

    remaining = [item for item in items if item.key not in grouped_keys and item.normalized_title]
    for left_idx, left in enumerate(remaining):
        for right in remaining[left_idx + 1 :]:
            score = fuzz.ratio(left.normalized_title, right.normalized_title) / 100
            if score < 0.94:
                continue
            groups.append(
                _make_group(len(groups) + 1, [left, right], "possible_fuzzy_title")
            )
            grouped_keys.update({left.key, right.key})
            break

    return groups


def build_dedupe_plan(
    items: list[EnrichedZoteroItem],
    source_jsonl: str,
) -> DedupePlan:
    return DedupePlan(source_jsonl=source_jsonl, groups=detect_duplicate_groups(items))


def _web_client_from_env() -> ZoteroWebClient | None:
    user_id = os.environ.get("ZOTERO_USER_ID")
    api_key = os.environ.get("ZOTERO_API_KEY")
    if not user_id or not api_key:
        return None
    return ZoteroWebClient(user_id=user_id, api_key=api_key)


def hydrate_reading_activity_from_zotero(
    items: list[EnrichedZoteroItem],
    local_base_url: str = DEFAULT_LOCAL_API_BASE_URL,
    library_prefix: str = DEFAULT_LIBRARY_PREFIX,
) -> list[EnrichedZoteroItem]:
    if any(item.reading_activity.has_reading_work or item.reading_activity.score for item in items):
        return items

    web_client = _web_client_from_env()
    try:
        try:
            with ZoteroLocalClient(base_url=local_base_url, library_prefix=library_prefix) as client:
                for item in items:
                    children = client.get_item_children(item.key)
                    item.reading_activity = client.collect_parent_reading_activity(
                        children,
                        web_client=web_client,
                    )
                return items
        except Exception:
            if web_client is None:
                return items
            for item in items:
                children = web_client.get_item_children(item.key)
                attachment_annotations: dict[str, list[dict[str, Any]]] = {}
                for child in children:
                    data = child.get("data", {})
                    if data.get("itemType") == "attachment":
                        attachment_annotations[str(child.get("key") or data.get("key"))] = (
                            web_client.get_attachment_annotations(
                                str(child.get("key") or data.get("key"))
                            )
                        )
                from paperflow.reading_activity import collect_reading_activity_from_children

                item.reading_activity = collect_reading_activity_from_children(
                    children,
                    attachment_annotations,
                )
            return items
    finally:
        if web_client is not None:
            web_client.close()


def write_dedupe_report(plan: DedupePlan, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# dedupe report",
        "",
        f"- Duplicate groups: {len(plan.groups)}",
        f"- Duplicate candidates: {len(plan.duplicate_candidate_keys)}",
        "",
        "## Duplicate resolution policy",
        "",
        "- Reading work is preserved first.",
        "- Metadata quality is used only after reading work.",
        "- No duplicate is deleted automatically.",
        "",
        "## Duplicate groups",
        "",
    ]
    for group in plan.groups:
        title = group.normalized_title or group.group_id
        lines.extend(
            [
                f"### {title}",
                "",
                f"Canonical: {group.canonical_item_key}",
                "",
                "Reason:",
                group.canonical_reason,
                "",
                "Items:",
            ]
        )
        for item in group.items:
            pdf = "yes" if item.has_pdf_attachment else "no"
            unsafe = "yes" if item.unsafe_to_delete and not item.is_canonical else "no"
            lines.extend(
                [
                    f"- {item.item_key}",
                    f"  - reading work: {_reading_summary(item.reading_activity)}",
                    f"  - metadata score: {item.metadata_quality_score}",
                    f"  - PDF: {pdf}",
                    f"  - unsafe to delete: {unsafe}",
                ]
            )
        lines.extend(
            [
                "",
                f"Metadata merge suggested: {'yes' if group.metadata_merge_suggested else 'no'}",
                "",
                "Recommended:",
                (
                    f"Keep {group.canonical_item_key} as canonical, copy missing metadata "
                    f"from {group.suggested_metadata_source_item_key}, then review duplicates manually."
                    if group.metadata_merge_suggested
                    else f"Keep {group.canonical_item_key} as canonical and review duplicates manually."
                ),
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def load_items_for_dedupe(path: Path) -> list[EnrichedZoteroItem]:
    try:
        items = read_jsonl_model(path, EnrichedZoteroItem)
        if any(item.title and not item.normalized_title for item in items):
            items = enrich_items(items)
    except ValueError:
        items = enrich_items(read_jsonl_model(path, ZoteroItem))
    return hydrate_reading_activity_from_zotero(items)


def detect_duplicates_file(
    input_path: Path,
    output_path: Path,
    report_path: Path,
) -> DedupePlan:
    items = load_items_for_dedupe(input_path)
    plan = build_dedupe_plan(items, source_jsonl=str(input_path))
    write_json(output_path, plan)
    write_dedupe_report(plan, report_path)
    return plan
