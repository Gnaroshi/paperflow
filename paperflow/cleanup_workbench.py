from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from paperflow.credentials import GeminiClient
from paperflow.metadata import DOI_RE, arxiv_id_from_doi, arxiv_id_from_url, detect_arxiv_id
from paperflow.migration_models import DedupePlan, EnrichedZoteroItem, MigrationPlan
from paperflow.pdf_text import extract_pdf_snippet
from paperflow.taxonomy_v2 import (
    MISSING_ABSTRACT_COLLECTION,
    MISSING_METADATA_COLLECTION,
    NON_PAPER_COLLECTION,
    normalize_doi,
)
from paperflow.utils import ensure_parent_dir, read_json_model, read_jsonl_model
from paperflow.zotero_web import ZoteroWebClient


ABSTRACT_CONFIRMATION = "APPLY ABSTRACT REPAIRS"
METADATA_CONFIRMATION = "APPLY METADATA REPAIRS"
DUPLICATE_DELETE_CONFIRMATION = "DELETE DUPLICATE ITEM"


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = text.replace("-\n", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_workbench_inputs(
    migration_plan_path: Path = Path("data/migration_plan.json"),
    enriched_path: Path = Path("data/zotero_items_enriched.jsonl"),
) -> tuple[MigrationPlan, dict[str, EnrichedZoteroItem]]:
    plan = read_json_model(migration_plan_path, MigrationPlan)
    items = {item.key: item for item in read_jsonl_model(enriched_path, EnrichedZoteroItem)}
    return plan, items


def cleanup_item_keys(plan: MigrationPlan, collection: str, tag: str) -> set[str]:
    return {
        item.item_key
        for item in plan.items
        if collection in item.target_collections or tag in item.normalized_tags
    }


def low_confidence_keys(plan: MigrationPlan, threshold: float = 0.55) -> set[str]:
    return {item.item_key for item in plan.items if item.confidence < threshold}


def non_paper_keys(plan: MigrationPlan) -> set[str]:
    return cleanup_item_keys(plan, NON_PAPER_COLLECTION, "cleanup/non-paper")


def extract_abstract_from_text(text: str) -> dict[str, Any]:
    cleaned = text.replace("\r", "\n")
    match = re.search(
        r"(?is)\b(?:abstract|summary)\b\s*[:.\-]?\s+(?P<body>.+?)(?=\n\s*(?:keywords?\b|1\s+introduction\b|introduction\b|i\.\s+introduction\b)|$)",
        cleaned,
    )
    if not match:
        return {"found": False, "abstract_text": "", "confidence": 0.0}
    body = normalize_text(match.group("body"))
    if len(body) < 80:
        return {"found": False, "abstract_text": "", "confidence": 0.0}
    return {
        "found": True,
        "abstract_text": body[:4000],
        "confidence": 0.86 if len(body) > 180 else 0.7,
    }


def abstract_text_is_verbatim(source_text: str, abstract_text: str) -> bool:
    source = normalize_text(source_text).lower()
    candidate = normalize_text(abstract_text).lower()
    return bool(candidate and len(candidate) >= 80 and candidate in source)


def gemini_extract_abstract_from_text(
    title: str | None,
    pdf_text: str,
    gemini: GeminiClient,
) -> dict[str, Any]:
    prompt = (
        "Extract the abstract verbatim from the provided paper text. "
        "Return strict JSON with keys found, abstract_text, evidence_source, confidence. "
        "If no abstract section is present, return found=false and abstract_text=\"NOT_FOUND\". "
        "Do not summarize or invent.\n\n"
        f"Title: {title or ''}\n\nTEXT:\n{pdf_text[:12000]}"
    )
    result = gemini.generate(prompt)
    if not result.get("ok"):
        return {"found": False, "error": result}
    raw = result.get("raw") or {}
    try:
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        payload = json.loads(text)
    except Exception:
        return {"found": False, "error": {"error_type": "invalid_gemini_json"}}
    abstract_text = normalize_text(payload.get("abstract_text"))
    if not payload.get("found") or abstract_text == "NOT_FOUND":
        return {"found": False, "abstract_text": "", "confidence": 0.0}
    if not abstract_text_is_verbatim(pdf_text, abstract_text):
        return {"found": False, "abstract_text": "", "confidence": 0.0, "rejected": "not_verbatim"}
    return {
        "found": True,
        "abstract_text": abstract_text,
        "evidence_source": "gemini_pdf_extract",
        "confidence": min(float(payload.get("confidence") or 0.75), 0.9),
    }


def fetch_arxiv_abstract(arxiv_id: str, client: httpx.Client | None = None) -> str | None:
    close = client is None
    client = client or httpx.Client(timeout=20)
    try:
        response = client.get("https://export.arxiv.org/api/query", params={"id_list": arxiv_id})
        response.raise_for_status()
        match = re.search(r"<summary>\s*(.*?)\s*</summary>", response.text, flags=re.S)
        return normalize_text(match.group(1)) if match else None
    except Exception:
        return None
    finally:
        if close:
            client.close()


def fetch_crossref_metadata(doi: str, client: httpx.Client | None = None) -> dict[str, Any]:
    close = client is None
    client = client or httpx.Client(timeout=20)
    try:
        response = client.get(f"https://api.crossref.org/works/{doi}")
        response.raise_for_status()
        message = response.json().get("message") or {}
        abstract = normalize_text(message.get("abstract"))
        return {
            "abstract": abstract or None,
            "title": (message.get("title") or [None])[0],
            "year": ((message.get("published-print") or message.get("published-online") or {}).get("date-parts") or [[None]])[0][0],
            "publication_title": (message.get("container-title") or [None])[0],
            "url": message.get("URL"),
        }
    except Exception:
        return {}
    finally:
        if close:
            client.close()


def first_pdf_text(item: EnrichedZoteroItem, max_chars: int = 12000) -> str:
    snippets: list[str] = []
    for attachment in item.attachments:
        if attachment.is_pdf and attachment.local_path:
            snippets.append(extract_pdf_snippet(attachment.local_path, max_chars=max_chars))
    return "\n".join(snippets)


def build_abstract_repair_plan(
    migration_plan_path: Path = Path("data/migration_plan.json"),
    enriched_path: Path = Path("data/zotero_items_enriched.jsonl"),
    enable_gemini: bool = False,
    gemini_model: str = "gemini-2.5-flash",
) -> dict[str, Any]:
    plan, enriched = load_workbench_inputs(migration_plan_path, enriched_path)
    target_keys = cleanup_item_keys(plan, MISSING_ABSTRACT_COLLECTION, "cleanup/missing-abstract")
    repairs: list[dict[str, Any]] = []
    gemini = GeminiClient(model=gemini_model) if enable_gemini else None
    try:
        for item_key in sorted(target_keys):
            item = enriched.get(item_key)
            migration_item = next((row for row in plan.items if row.item_key == item_key), None)
            if not item or not migration_item:
                continue
            before = normalize_text(item.abstract_note)
            candidate = {
                "found": False,
                "abstract_text": "",
                "evidence_source": None,
                "confidence": 0.0,
            }
            if before:
                candidate = {
                    "found": True,
                    "abstract_text": before,
                    "evidence_source": "zotero",
                    "confidence": 1.0,
                }
            elif item.arxiv_id and (arxiv_id_from_doi(item.doi_normalized) or arxiv_id_from_url(item.url)):
                abstract = fetch_arxiv_abstract(item.arxiv_id)
                if abstract:
                    candidate = {
                        "found": True,
                        "abstract_text": abstract,
                        "evidence_source": "arxiv",
                        "confidence": 0.95,
                    }
            elif item.doi_normalized:
                metadata = fetch_crossref_metadata(item.doi_normalized)
                if metadata.get("abstract"):
                    candidate = {
                        "found": True,
                        "abstract_text": metadata["abstract"],
                        "evidence_source": "doi",
                        "confidence": 0.88,
                    }
            if not candidate["found"]:
                pdf_text = first_pdf_text(item)
                extracted = extract_abstract_from_text(pdf_text)
                if extracted["found"]:
                    candidate = {
                        **extracted,
                        "evidence_source": "pdf",
                    }
                elif enable_gemini and gemini is not None and pdf_text:
                    gemini_result = gemini_extract_abstract_from_text(item.title, pdf_text, gemini)
                    if gemini_result.get("found"):
                        candidate = gemini_result
            repairs.append(
                {
                    "item_key": item.key,
                    "title": item.title,
                    "current_abstract": before,
                    "proposed_abstract": candidate["abstract_text"],
                    "found": candidate["found"],
                    "evidence_source": candidate.get("evidence_source"),
                    "confidence": candidate["confidence"],
                    "high_confidence": candidate["found"] and candidate["confidence"] >= 0.8,
                    "target_collections": migration_item.target_collections,
                    "normalized_tags": migration_item.normalized_tags,
                }
            )
    finally:
        if gemini is not None:
            gemini.close()
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repairs": repairs,
    }


def write_abstract_repair_report(plan: dict[str, Any], path: Path) -> None:
    ensure_parent_dir(path)
    lines = [
        "# abstract repair report",
        "",
        f"- Items reviewed: {len(plan['repairs'])}",
        f"- High-confidence repairs: {sum(1 for row in plan['repairs'] if row['high_confidence'])}",
        "",
    ]
    for row in plan["repairs"]:
        lines.append(
            f"- {row['item_key']} | {row.get('title') or '(untitled)'} | "
            f"found={row['found']} | source={row.get('evidence_source')} | confidence={row['confidence']}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_abstract_apply(apply: bool, confirm: str | None) -> None:
    if not apply:
        raise ValueError("Refusing abstract repair apply: --apply is required.")
    if confirm != ABSTRACT_CONFIRMATION:
        raise ValueError(f'Refusing abstract repairs: --confirm "{ABSTRACT_CONFIRMATION}" is required.')


def apply_abstract_repairs(
    plan: dict[str, Any],
    user_id: str,
    api_key: str,
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with ZoteroWebClient(user_id=user_id, api_key=api_key) as client:
        for row in plan["repairs"]:
            if not row.get("high_confidence"):
                events.append({"event": "abstract-repair-skipped", "itemKey": row["item_key"]})
                continue
            raw = client.get_json(f"items/{row['item_key']}", params={"format": "json"})
            data = raw.get("data", {})
            existing = normalize_text(data.get("abstractNote"))
            if existing and not overwrite:
                events.append({"event": "abstract-repair-skipped-existing", "itemKey": row["item_key"]})
                continue
            tags = [
                tag
                for tag in data.get("tags", [])
                if (tag.get("tag") if isinstance(tag, dict) else tag) != "cleanup/missing-abstract"
            ]
            body = {"abstractNote": row["proposed_abstract"], "tags": tags}
            response = client.patch_item(row["item_key"], body, version=raw.get("version"))
            events.append(
                {
                    "event": "abstract-updated",
                    "itemKey": row["item_key"],
                    "statusCode": response.status_code,
                }
            )
    return events


def build_metadata_repair_plan(
    migration_plan_path: Path = Path("data/migration_plan.json"),
    enriched_path: Path = Path("data/zotero_items_enriched.jsonl"),
) -> dict[str, Any]:
    plan, enriched = load_workbench_inputs(migration_plan_path, enriched_path)
    target_keys = cleanup_item_keys(plan, MISSING_METADATA_COLLECTION, "cleanup/missing-metadata")
    repairs: list[dict[str, Any]] = []
    for item_key in sorted(target_keys):
        item = enriched.get(item_key)
        if not item:
            continue
        pdf_text = first_pdf_text(item)
        doi_match = DOI_RE.search(pdf_text)
        doi = normalize_doi(doi_match.group(0)) if doi_match else item.doi_normalized
        arxiv_id = detect_arxiv_id(item, doi)
        updates: dict[str, Any] = {}
        if doi and doi != item.doi_normalized:
            updates["doi_normalized"] = {"before": item.doi_normalized, "after": doi}
        if arxiv_id and arxiv_id != item.arxiv_id:
            updates["arxiv_id"] = {"before": item.arxiv_id, "after": arxiv_id}
        crossref = fetch_crossref_metadata(doi) if doi else {}
        if crossref.get("url") and not item.url:
            updates["url"] = {"before": item.url, "after": crossref["url"]}
        if crossref.get("year") and not item.year:
            updates["year"] = {"before": item.year, "after": crossref["year"]}
        if crossref.get("publication_title") and not item.publication_title:
            updates["publication_title"] = {
                "before": item.publication_title,
                "after": crossref["publication_title"],
            }
        if crossref.get("abstract") and not item.abstract_note:
            updates["abstract"] = {"before": item.abstract_note, "after": crossref["abstract"]}
        repairs.append(
            {
                "item_key": item.key,
                "title": item.title,
                "updates": updates,
                "approved_fields": list(updates),
                "safe_to_apply": bool(updates),
            }
        )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repairs": repairs,
    }


def write_metadata_repair_report(plan: dict[str, Any], path: Path) -> None:
    ensure_parent_dir(path)
    lines = [
        "# metadata repair report",
        "",
        f"- Items reviewed: {len(plan['repairs'])}",
        f"- Items with proposed changes: {sum(1 for row in plan['repairs'] if row['updates'])}",
        "",
    ]
    for row in plan["repairs"]:
        fields = ", ".join(row["updates"].keys()) or "none"
        lines.append(f"- {row['item_key']} | {row.get('title') or '(untitled)'} | fields: {fields}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_metadata_apply(apply: bool, confirm: str | None) -> None:
    if not apply:
        raise ValueError("Refusing metadata repair apply: --apply is required.")
    if confirm != METADATA_CONFIRMATION:
        raise ValueError(f'Refusing metadata repairs: --confirm "{METADATA_CONFIRMATION}" is required.')


def apply_metadata_repairs(
    plan: dict[str, Any],
    user_id: str,
    api_key: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with ZoteroWebClient(user_id=user_id, api_key=api_key) as client:
        for row in plan["repairs"]:
            updates = row.get("updates") or {}
            if not updates:
                events.append({"event": "metadata-repair-skipped", "itemKey": row["item_key"]})
                continue
            raw = client.get_json(f"items/{row['item_key']}", params={"format": "json"})
            data = raw.get("data", {})
            body: dict[str, Any] = {}
            if "doi_normalized" in updates and not normalize_doi(data.get("DOI") or data.get("doi")):
                body["DOI"] = updates["doi_normalized"]["after"]
            if "url" in updates and not data.get("url"):
                body["url"] = updates["url"]["after"]
            if "year" in updates and not data.get("date"):
                body["date"] = str(updates["year"]["after"])
            if "publication_title" in updates and not data.get("publicationTitle"):
                body["publicationTitle"] = updates["publication_title"]["after"]
            if "abstract" in updates and not normalize_text(data.get("abstractNote")):
                body["abstractNote"] = updates["abstract"]["after"]
            if "arxiv_id" in updates:
                extra = data.get("extra") or ""
                if "arxiv" not in extra.lower():
                    body["extra"] = (extra + "\n" if extra else "") + f"arXiv: {updates['arxiv_id']['after']}"
            if not body:
                events.append({"event": "metadata-repair-no-stronger-fields", "itemKey": row["item_key"]})
                continue
            response = client.patch_item(row["item_key"], body, version=raw.get("version"))
            events.append(
                {
                    "event": "metadata-updated",
                    "itemKey": row["item_key"],
                    "fields": sorted(body),
                    "statusCode": response.status_code,
                }
            )
    return events


def duplicate_resolution_plan(
    dedupe_path: Path = Path("data/dedupe_plan.json"),
    migration_path: Path = Path("data/migration_plan.json"),
) -> dict[str, Any]:
    dedupe = read_json_model(dedupe_path, DedupePlan)
    migration = read_json_model(migration_path, MigrationPlan)
    migration_by_key = {item.item_key: item for item in migration.items}
    groups: list[dict[str, Any]] = []
    for group in dedupe.groups:
        items: list[dict[str, Any]] = []
        for item in group.items:
            migration_item = migration_by_key.get(item.item_key)
            items.append(
                {
                    **item.model_dump(),
                    "current_collections": migration_item.existing_collection_keys if migration_item else [],
                    "planned_collections": migration_item.target_collections if migration_item else [],
                    "unsafe_to_delete": item.unsafe_to_delete,
                }
            )
        groups.append(
            {
                "group_id": group.group_id,
                "normalized_title": group.normalized_title,
                "match_type": group.match_type,
                "canonical_item_key": group.canonical_item_key,
                "recommended_action": group.recommended_action,
                "metadata_merge_suggested": group.metadata_merge_suggested,
                "suggested_metadata_source_item_key": group.suggested_metadata_source_item_key,
                "items": items,
            }
        )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "groups": groups,
    }


def write_duplicate_resolution_report(plan: dict[str, Any], path: Path) -> None:
    ensure_parent_dir(path)
    lines = ["# duplicate resolution report", "", f"- Groups: {len(plan['groups'])}", ""]
    for group in plan["groups"]:
        lines.append(
            f"## {group['normalized_title']}\n\n"
            f"- Match type: {group['match_type']}\n"
            f"- Canonical: {group['canonical_item_key']}\n"
            f"- Metadata merge suggested: {group['metadata_merge_suggested']}\n"
        )
        for item in group["items"]:
            lines.append(
                f"- {item['item_key']} | canonical={item['is_canonical']} | "
                f"unsafe_to_delete={item['unsafe_to_delete']}"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_duplicate_delete(confirm: str | None, item: dict[str, Any]) -> None:
    if confirm != DUPLICATE_DELETE_CONFIRMATION:
        raise ValueError(f'Refusing duplicate deletion: confirm "{DUPLICATE_DELETE_CONFIRMATION}".')
    if item.get("unsafe_to_delete"):
        raise ValueError("Refusing duplicate deletion: duplicate has reading work.")


def explain_item(
    item_key: str,
    migration_path: Path = Path("data/migration_plan.json"),
    preview_path: Path = Path("data/apply_preview.json"),
) -> dict[str, Any]:
    migration = read_json_model(migration_path, MigrationPlan)
    row = next((item for item in migration.items if item.item_key == item_key), None)
    if row is None:
        raise ValueError(f"Unknown item key in migration plan: {item_key}")
    preview = _load_json(preview_path) if preview_path.exists() else {}
    update = next((item for item in preview.get("item_updates", []) if item.get("itemKey") == item_key), {})
    return {
        "item_key": item_key,
        "title": row.title,
        "old_collections": row.existing_collection_keys,
        "new_collections": row.target_collections,
        "added_tags": update.get("tagsAdded", []),
        "removed_tags": update.get("tagsRemoved", []),
        "cleanup_flags": [tag for tag in row.normalized_tags if tag.startswith("cleanup/")],
        "duplicate_of": row.canonical_item_key,
        "confidence": row.confidence,
        "rationale": row.rationale,
        "apply_status": "planned" if update else "unknown",
    }


def migration_audit(
    migration_path: Path = Path("data/migration_plan.json"),
    preview_path: Path = Path("data/apply_preview.json"),
    apply_log_glob: str = "data/apply_log_*.json",
) -> dict[str, Any]:
    migration = read_json_model(migration_path, MigrationPlan)
    preview = _load_json(preview_path) if preview_path.exists() else {}
    update_keys = {row.get("itemKey") for row in preview.get("item_updates", [])}
    applied_keys: set[str] = set()
    glob_path = Path(apply_log_glob)
    log_paths = (
        glob_path.parent.glob(glob_path.name)
        if glob_path.is_absolute()
        else Path(".").glob(apply_log_glob)
    )
    for log_path in log_paths:
        log = _load_json(log_path)
        for event in log.get("events", []):
            if event.get("event") == "item-updated":
                applied_keys.add(event.get("itemKey"))
    items_in_ai = [item.item_key for item in migration.items if item.target_collections]
    items_not_in_ai = [item.item_key for item in migration.items if not item.target_collections]
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items_successfully_moved": sorted(applied_keys),
        "items_still_in_old_collections": sorted(set(update_keys) - applied_keys),
        "items_in_ai_library": items_in_ai,
        "items_not_in_ai_library": items_not_in_ai,
        "old_collections_with_remaining_parent_items": preview.get(
            "old_collections_that_would_be_empty", []
        ),
        "failed_item_updates": sorted(set(update_keys) - applied_keys),
        "duplicate_cleanup_status": {
            "candidate_count": migration.stats.duplicate_candidates,
        },
        "missing_abstract_repair_status": "see data/abstract_repair_plan.json",
        "missing_metadata_repair_status": "see data/metadata_repair_plan.json",
    }


def write_migration_audit_report(audit: dict[str, Any], path: Path) -> None:
    ensure_parent_dir(path)
    lines = [
        "# migration audit",
        "",
        f"- Items successfully moved: {len(audit['items_successfully_moved'])}",
        f"- Items still in old collections: {len(audit['items_still_in_old_collections'])}",
        f"- Items in AI Library: {len(audit['items_in_ai_library'])}",
        f"- Items not in AI Library: {len(audit['items_not_in_ai_library'])}",
        f"- Failed item updates: {len(audit['failed_item_updates'])}",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
