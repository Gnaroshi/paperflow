from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pypdf import PdfReader
from rapidfuzz import fuzz

from paperflow.credentials import DEFAULT_GEMINI_MODEL, GeminiClient
from paperflow.gemini_classifier import classify_with_gemini
from paperflow.ingest import (
    _created_key,
    _find_existing_parent,
    _zotero_open_uri,
    arxiv_id_from_filename_preserve_version,
    copy_pdf_to_vault,
    linked_attachment_body,
)
from paperflow.metadata import (
    DOI_RE,
    arxiv_id_from_doi,
    arxiv_id_from_extra,
    arxiv_id_from_url,
    normalize_arxiv_id,
)
from paperflow.metadata import enrich_item
from paperflow.migration_apply import collection_maps, creation_plan
from paperflow.taxonomy_v2 import normalize_doi
from paperflow.taxonomy_v3 import (
    AMBIGUOUS_CLASSIFICATION_COLLECTION,
    COLLECTION_TREE_V3,
    MISSING_ABSTRACT_REVIEW_COLLECTION,
    MISSING_METADATA_REVIEW_COLLECTION,
    NEW_ARXIV_VERSION_COLLECTION,
    POSSIBLE_ZOTERO_DUPLICATE_COLLECTION,
    REVIEW_QUEUE_COLLECTION,
    TAG_VOCABULARY_V3,
    area_slug_from_collection,
    clamp_tags_v3,
    normalize_title_v3,
    unique_preserve_order,
)
from paperflow.taxonomy_overrides import override_candidates_for_evidence, rag_unless_contains_terms
from paperflow.utils import ensure_parent_dir
from paperflow.vault import DEFAULT_VAULT_LIBRARY, safe_pdf_filename
from paperflow.zotero_local import (
    LOCAL_API_SETUP_MESSAGE,
    LocalAPIUnavailable,
    ZoteroLocalClient,
)
from paperflow.zotero_web import ZoteroWebClient


LOCAL_IMPORT_CONFIRMATION = "IMPORT LOCAL PAPERS"
SOURCE_QUARANTINE_CONFIRMATION = "MOVE IMPORTED SOURCE PDFS TO QUARANTINE"
MAX_FULL_HASH_BYTES = 100 * 1024 * 1024

TEMP_SUFFIXES = (
    ".download",
    ".crdownload",
    ".part",
    ".partial",
    ".tmp",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_path(path: Path, limit_bytes: int | None = None) -> str:
    digest = hashlib.sha256()
    remaining = limit_bytes
    with path.open("rb") as input_file:
        while True:
            if remaining is not None and remaining <= 0:
                break
            chunk_size = 1024 * 1024 if remaining is None else min(1024 * 1024, remaining)
            chunk = input_file.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
    return digest.hexdigest()


def is_hidden_path(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return any(part.startswith(".") for part in rel.parts)


def is_temporary_download(path: Path) -> bool:
    name = path.name
    if name == ".DS_Store" or name.startswith("._"):
        return True
    return name.lower().endswith(TEMP_SUFFIXES)


def depth_from_root(path: Path, root: Path) -> int:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return 0
    return max(0, len(rel.parts) - 1)


def glob_match(path: Path, patterns: list[str]) -> bool:
    text = str(path)
    return any(fnmatch.fnmatch(text, pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in patterns)


def title_from_filename(path: Path) -> str:
    stem = re.sub(r"(?i)arxiv", " ", path.stem)
    stem = re.sub(r"\b\d{4}\.\d{4,5}v?\d*\b", " ", stem)
    stem = re.sub(r"10\.\d{4,9}.+", " ", stem)
    stem = re.sub(r"[_\-]+", " ", stem)
    return re.sub(r"\s+", " ", stem).strip()


def first_page_title(text: str) -> str | None:
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
        if re.sub(r"\s+", " ", line).strip()
    ]
    for line in lines[:16]:
        lowered = line.lower()
        if lowered.startswith(("abstract", "keywords", "arxiv:", "published", "submitted")):
            continue
        if "@" in line or len(line) > 180:
            continue
        if 2 <= len(line.split()) <= 18 and any(char.isalpha() for char in line):
            return line.title() if line.isupper() else line
    return None


def abstract_from_first_pages(text: str) -> str | None:
    match = re.search(
        r"(?is)\b(?:abstract|summary)\b\s*[:.\-]?\s+(?P<body>.+?)(?=\n\s*(?:1\s+introduction\b|introduction\b|keywords?\b)|$)",
        text,
    )
    if not match:
        return None
    abstract = re.sub(r"(?<=\w)-\s+(?=\w)", "", match.group("body"))
    abstract = re.sub(r"\s+", " ", abstract).strip()
    return abstract if len(abstract) >= 80 else None


def arxiv_id_with_version(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(
        r"(?<![\d.])(?P<id>(?:\d{2})(?:0[1-9]|1[0-2])\.\d{4,5}(?:v\d+)?)(?![\d.])",
        value,
        flags=re.IGNORECASE,
    )
    return match.group("id").lower() if match else None


def arxiv_base(value: str | None) -> str | None:
    normalized = normalize_arxiv_id(value)
    return normalized or None


def arxiv_version(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"v(\d+)$", value, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def scan_pdf_metadata(path: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    first_pages_text = ""
    pdf_title = None
    pdf_author = None
    page_count = None
    try:
        reader = PdfReader(str(path))
        page_count = len(reader.pages)
        raw = reader.metadata or {}
        pdf_title = str(raw.get("/Title")).strip() if raw.get("/Title") else None
        pdf_author = str(raw.get("/Author")).strip() if raw.get("/Author") else None
        texts = []
        for page in reader.pages[:3]:
            try:
                texts.append(page.extract_text() or "")
            except Exception as exc:
                errors.append(f"page-text-error: {exc}")
        first_pages_text = "\n".join(texts)[:12000]
    except Exception as exc:
        errors.append(f"pdf-read-error: {exc}")

    combined = " ".join([path.name, pdf_title or "", pdf_author or "", first_pages_text])
    doi_candidates = [normalize_doi(match.group(0)) for match in DOI_RE.finditer(combined)]
    doi_candidates = [doi for doi in unique_preserve_order(doi_candidates) if doi]
    arxiv_candidates = [
        arxiv_id_from_filename_preserve_version(path.name),
        arxiv_id_with_version(combined),
        arxiv_id_from_doi(doi_candidates[0] if doi_candidates else None),
        arxiv_id_from_url(combined),
        arxiv_id_from_extra(combined),
    ]
    arxiv_candidates = [candidate for candidate in unique_preserve_order(arxiv_candidates) if candidate]
    title_candidates = [
        first_page_title(first_pages_text),
        pdf_title,
        title_from_filename(path),
    ]
    title_candidates = [candidate for candidate in unique_preserve_order(title_candidates) if candidate]
    abstract = abstract_from_first_pages(first_pages_text)
    year = None
    year_match = re.search(r"\b(19|20)\d{2}\b", combined)
    if year_match:
        year = int(year_match.group(0))
    return (
        {
            "page_count": page_count,
            "first_pages_text": first_pages_text,
            "pdf_metadata_title": pdf_title,
            "pdf_metadata_author": pdf_author,
            "title_candidates": title_candidates,
            "doi_candidates": doi_candidates,
            "arxiv_id_candidates": arxiv_candidates,
            "first_page_abstract_candidate": abstract,
            "detected": {
                "arxiv_id": arxiv_candidates[0] if arxiv_candidates else None,
                "doi": doi_candidates[0] if doi_candidates else None,
                "title": title_candidates[0] if title_candidates else None,
                "year": year,
                "abstract_present": bool(abstract),
            },
        },
        errors,
    )


def emit_progress(enabled: bool, event: str, message: str, **extra: Any) -> None:
    if enabled:
        payload = {"event": event, "message": message, "elapsed_ms": int(time.monotonic() * 1000)}
        payload.update(extra)
        print(json.dumps(payload, ensure_ascii=False), flush=True)


def local_scan(
    root_path: Path,
    recursive: bool = True,
    include_hidden: bool = False,
    max_depth: int | None = None,
    follow_symlinks: bool = False,
    exclude_glob: list[str] | None = None,
    include_glob: list[str] | None = None,
    min_size_kb: int = 1,
    max_size_mb: int | None = None,
    progress_jsonl: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    root = root_path.expanduser().resolve()
    exclude_glob = exclude_glob or []
    include_glob = include_glob or []
    files: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    seen_full_hashes: dict[str, str] = {}
    candidates: list[Path] = []

    if root.is_file():
        candidates = [root]
    elif recursive:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
            current_dir = Path(dirpath)
            if not include_hidden:
                dirnames[:] = [name for name in dirnames if not name.startswith(".")]
            if max_depth is not None and depth_from_root(current_dir, root) >= max_depth:
                dirnames[:] = []
            for filename in filenames:
                candidates.append(current_dir / filename)
    else:
        candidates = [path for path in root.iterdir() if path.is_file()]

    emit_progress(progress_jsonl, "stage_started", f"Scanning {len(candidates)} candidate files")
    for path in sorted(candidates):
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path.absolute()
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        if is_temporary_download(path):
            continue
        if not include_hidden and is_hidden_path(path, root):
            continue
        if include_glob and not glob_match(path, include_glob):
            continue
        if exclude_glob and glob_match(path, exclude_glob):
            continue
        if path.suffix.lower() != ".pdf":
            continue

        errors: list[str] = []
        row: dict[str, Any] = {
            "path": str(path.absolute()),
            "resolved_path": str(resolved),
            "filename": path.name,
            "scan_status": "ok",
            "errors": errors,
        }
        try:
            stat = path.stat()
            size = stat.st_size
            row.update(
                {
                    "size_bytes": size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                }
            )
            if size == 0:
                row["scan_status"] = "skipped"
                errors.append("zero-byte-file")
                files.append(row)
                continue
            if size < min_size_kb * 1024:
                row["scan_status"] = "skipped"
                errors.append("below-min-size")
                files.append(row)
                continue
            if max_size_mb is not None and size > max_size_mb * 1024 * 1024:
                row["scan_status"] = "skipped"
                errors.append("above-max-size")
                files.append(row)
                continue
            row["sha256_first_1mb"] = sha256_path(path, 1024 * 1024)
            row["sha256"] = sha256_path(path) if size <= MAX_FULL_HASH_BYTES else None
            if row["sha256"] and row["sha256"] in seen_full_hashes:
                row["scan_status"] = "skipped"
                errors.append(f"duplicate-file-hash-of:{seen_full_hashes[row['sha256']]}")
                files.append(row)
                continue
            if row["sha256"]:
                seen_full_hashes[row["sha256"]] = str(path.absolute())
            metadata, metadata_errors = scan_pdf_metadata(path)
            errors.extend(metadata_errors)
            row.update(metadata)
            emit_progress(progress_jsonl, "file_scanned", path.name, path=str(path), status=row["scan_status"])
        except Exception as exc:
            row["scan_status"] = "error"
            errors.append(str(exc))
        if verbose and row["errors"]:
            emit_progress(progress_jsonl, "warning", f"{path.name}: {row['errors']}", path=str(path))
        files.append(row)

    plan = {
        "schema_version": "1.0",
        "root_path": str(root),
        "generated_at": utc_now(),
        "files": files,
    }
    emit_progress(progress_jsonl, "done", f"Scanned {len(files)} PDF rows")
    return plan


def write_local_scan_report(plan: dict[str, Any], markdown_output: Path, csv_output: Path) -> None:
    ensure_parent_dir(markdown_output)
    rows = plan.get("files", [])
    ok = sum(1 for row in rows if row.get("scan_status") == "ok")
    skipped = sum(1 for row in rows if row.get("scan_status") == "skipped")
    errors = sum(1 for row in rows if row.get("scan_status") == "error")
    lines = [
        "# local scan report",
        "",
        f"- Root: `{plan.get('root_path')}`",
        f"- Files: {len(rows)}",
        f"- OK: {ok}",
        f"- Skipped: {skipped}",
        f"- Error: {errors}",
        "",
        "## Files",
        "",
    ]
    for row in rows:
        lines.append(
            f"- {row.get('scan_status')}: `{row.get('path')}` | "
            f"{row.get('detected', {}).get('title') or '(untitled)'}"
        )
    markdown_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ensure_parent_dir(csv_output)
    pd.DataFrame(
        [
            {
                "path": row.get("path"),
                "filename": row.get("filename"),
                "size_bytes": row.get("size_bytes"),
                "scan_status": row.get("scan_status"),
                "title": row.get("detected", {}).get("title"),
                "doi": row.get("detected", {}).get("doi"),
                "arxiv_id": row.get("detected", {}).get("arxiv_id"),
                "year": row.get("detected", {}).get("year"),
                "page_count": row.get("page_count"),
                "errors": "; ".join(row.get("errors", [])),
            }
            for row in rows
        ]
    ).to_csv(csv_output, index=False)


def creator_names(creators: list[Any]) -> list[str]:
    names = []
    for creator in creators:
        if isinstance(creator, dict):
            name = creator.get("name") or " ".join(
                part for part in [creator.get("firstName"), creator.get("lastName")] if part
            )
        else:
            name = getattr(creator, "name", None) or " ".join(
                part for part in [getattr(creator, "first_name", None), getattr(creator, "last_name", None)] if part
            )
        if name:
            names.append(name.strip())
    return names


def first_author_key(names: list[str]) -> str:
    cleaned = [name for name in names if name and name.strip()]
    if not cleaned:
        return ""
    last = cleaned[0].split()[-1]
    return re.sub(r"[^a-z0-9]+", "", last.lower())


def attachment_hashes(path_value: str | None) -> dict[str, str | None]:
    if not path_value:
        return {"sha256": None, "sha256_first_1mb": None}
    path = Path(path_value).expanduser()
    if not path.exists() or not path.is_file():
        return {"sha256": None, "sha256_first_1mb": None}
    size = path.stat().st_size
    return {
        "sha256": sha256_path(path) if size <= MAX_FULL_HASH_BYTES else None,
        "sha256_first_1mb": sha256_path(path, 1024 * 1024),
    }


def zotero_item_to_index_row(item: Any) -> dict[str, Any]:
    enriched = enrich_item(item)
    creators = creator_names(item.creators)
    attachments = []
    for attachment in item.attachments:
        hashes = attachment_hashes(attachment.local_path)
        attachments.append(
            {
                "key": attachment.key,
                "filename": attachment.filename,
                "content_type": attachment.content_type,
                "local_path": attachment.local_path,
                **hashes,
            }
        )
    activity = item.reading_activity
    return {
        "item_key": item.key,
        "version": item.version,
        "title": item.title,
        "normalized_title": enriched.normalized_title,
        "creators": creators,
        "first_author": first_author_key(creators),
        "year": item.year,
        "doi": item.doi,
        "doi_normalized": enriched.doi_normalized,
        "arxiv_id": enriched.arxiv_id,
        "arxiv_base_id": arxiv_base(enriched.arxiv_id),
        "url": item.url,
        "abstractNote": item.abstract_note,
        "publicationTitle": item.publication_title,
        "itemType": item.item_type,
        "existing_tags": item.existing_tags,
        "existing_collections": item.existing_collection_keys,
        "child_attachments": attachments,
        "attachment_filenames": [row["filename"] for row in attachments if row.get("filename")],
        "attachment_paths": [row["local_path"] for row in attachments if row.get("local_path")],
        "attachment_sha256": [row["sha256"] for row in attachments if row.get("sha256")],
        "attachment_sha256_first_1mb": [row["sha256_first_1mb"] for row in attachments if row.get("sha256_first_1mb")],
        "child_note_count": activity.note_count,
        "annotation_count": activity.annotation_count,
        "highlight_count": activity.highlight_count,
        "underline_count": activity.underline_count,
        "reading_work_present": activity.has_reading_work,
    }


def raw_web_items_to_index(all_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    parents: list[dict[str, Any]] = []
    for raw in all_items:
        data = raw.get("data", {})
        parent = data.get("parentItem")
        if parent:
            children_by_parent.setdefault(str(parent), []).append(raw)
        elif data.get("itemType") not in {"attachment", "note"}:
            parents.append(raw)
    rows = []
    for raw in parents:
        data = raw.get("data", {})
        key = str(raw.get("key") or data.get("key"))
        children = children_by_parent.get(key, [])
        attachments = [
            child.get("data", {})
            for child in children
            if child.get("data", {}).get("itemType") == "attachment"
        ]
        notes = [child for child in children if child.get("data", {}).get("itemType") == "note"]
        creators = creator_names(data.get("creators", []))
        doi = normalize_doi(data.get("DOI") or data.get("doi"))
        arxiv_id = arxiv_id_from_doi(doi) or arxiv_id_from_url(data.get("url")) or arxiv_id_from_extra(data.get("extra"))
        row = {
            "item_key": key,
            "version": raw.get("version") or data.get("version"),
            "title": data.get("title"),
            "normalized_title": normalize_title_v3(data.get("title")),
            "creators": creators,
            "first_author": first_author_key(creators),
            "year": extract_year_from_text(data.get("date") or ""),
            "doi": data.get("DOI") or data.get("doi"),
            "doi_normalized": doi,
            "arxiv_id": arxiv_id,
            "arxiv_base_id": arxiv_base(arxiv_id),
            "url": data.get("url"),
            "abstractNote": data.get("abstractNote"),
            "publicationTitle": data.get("publicationTitle") or data.get("conferenceName"),
            "itemType": data.get("itemType"),
            "existing_tags": [tag.get("tag") for tag in data.get("tags", []) if tag.get("tag")],
            "existing_collections": data.get("collections", []),
            "child_attachments": attachments,
            "attachment_filenames": [row.get("filename") for row in attachments if row.get("filename")],
            "attachment_paths": [row.get("path") for row in attachments if row.get("path")],
            "attachment_sha256": [],
            "attachment_sha256_first_1mb": [],
            "child_note_count": len(notes),
            "annotation_count": 0,
            "highlight_count": 0,
            "underline_count": 0,
            "reading_work_present": bool(notes),
        }
        rows.append(row)
    return rows


def extract_year_from_text(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", value)
    return int(match.group(0)) if match else None


def jsonl_fallback_to_index(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        title = data.get("title")
        creators = creator_names(data.get("creators", []))
        doi = data.get("doi_normalized") or normalize_doi(data.get("doi"))
        arxiv_id = data.get("arxiv_id") or arxiv_id_from_doi(doi) or arxiv_id_from_url(data.get("url"))
        attachments = data.get("attachments", [])
        rows.append(
            {
                "item_key": data.get("key") or data.get("item_key"),
                "version": data.get("version"),
                "title": title,
                "normalized_title": data.get("normalized_title") or normalize_title_v3(title),
                "creators": creators,
                "first_author": first_author_key(creators),
                "year": data.get("year"),
                "doi": data.get("doi"),
                "doi_normalized": doi,
                "arxiv_id": arxiv_id,
                "arxiv_base_id": arxiv_base(arxiv_id),
                "url": data.get("url"),
                "abstractNote": data.get("abstract_note") or data.get("abstractNote"),
                "publicationTitle": data.get("publication_title") or data.get("publicationTitle"),
                "itemType": data.get("item_type") or data.get("itemType"),
                "existing_tags": data.get("existing_tags") or data.get("existingTags") or [],
                "existing_collections": data.get("existing_collection_keys") or data.get("existingCollectionKeys") or [],
                "child_attachments": attachments,
                "attachment_filenames": [row.get("filename") for row in attachments if row.get("filename")],
                "attachment_paths": [row.get("local_path") or row.get("localPath") for row in attachments if row.get("local_path") or row.get("localPath")],
                "attachment_sha256": [],
                "attachment_sha256_first_1mb": [],
                "child_note_count": data.get("note_count") or data.get("noteCount") or 0,
                "annotation_count": data.get("annotation_count") or data.get("annotationCount") or 0,
                "highlight_count": data.get("reading_activity", {}).get("highlight_count", 0),
                "underline_count": data.get("reading_activity", {}).get("underline_count", 0),
                "reading_work_present": data.get("reading_activity", {}).get("has_reading_work", False),
            }
        )
    return rows


def build_zotero_index(
    local_base_url: str,
    library_prefix: str,
    web_base_url: str,
    fallback_jsonl: Path = Path("data/zotero_items_enriched.jsonl"),
) -> dict[str, Any]:
    warnings: list[str] = []
    source = "local-api"
    try:
        with ZoteroLocalClient(base_url=local_base_url, library_prefix=library_prefix) as client:
            rows = [zotero_item_to_index_row(item) for item in client.scan_items()]
    except Exception as local_exc:
        user_id = os.environ.get("ZOTERO_USER_ID")
        api_key = os.environ.get("ZOTERO_API_KEY")
        if user_id and api_key:
            source = "web-api"
            warnings.append(f"Local API unavailable; used Web API fallback: {local_exc}")
            with ZoteroWebClient(user_id=user_id, api_key=api_key, base_url=web_base_url) as client:
                rows = raw_web_items_to_index(client.iter_items())
        elif fallback_jsonl.exists():
            source = "jsonl-fallback"
            warnings.append(f"API unavailable; used {fallback_jsonl}. {LOCAL_API_SETUP_MESSAGE}")
            rows = jsonl_fallback_to_index(fallback_jsonl)
        else:
            raise LocalAPIUnavailable(LOCAL_API_SETUP_MESSAGE) from local_exc
    return {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "source": source,
        "warnings": warnings,
        "items": rows,
    }


def write_zotero_index_report(index: dict[str, Any], output_path: Path) -> None:
    ensure_parent_dir(output_path)
    rows = index.get("items", [])
    lines = [
        "# zotero index report",
        "",
        f"- Source: {index.get('source')}",
        f"- Items: {len(rows)}",
        f"- Warnings: {len(index.get('warnings', []))}",
        "",
    ]
    lines.extend(f"- Warning: {warning}" for warning in index.get("warnings", []))
    lines.extend(["", "## Items", ""])
    for row in rows[:200]:
        lines.append(f"- {row.get('item_key')}: {row.get('title') or '(untitled)'}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def local_first_author(scan_row: dict[str, Any]) -> str:
    author = scan_row.get("pdf_metadata_author") or ""
    return first_author_key([author])


def title_values_for_scan(scan_row: dict[str, Any]) -> list[str]:
    detected = scan_row.get("detected", {})
    values = [
        detected.get("title"),
        *(scan_row.get("title_candidates") or []),
        title_from_filename(Path(scan_row.get("filename") or "")),
    ]
    return [value for value in unique_preserve_order(values) if value]


def best_title_similarity(scan_row: dict[str, Any], zotero_row: dict[str, Any]) -> int:
    ztitle = zotero_row.get("normalized_title") or normalize_title_v3(zotero_row.get("title"))
    if not ztitle:
        return 0
    return max(
        (
            fuzz.token_set_ratio(normalize_title_v3(title), ztitle)
            for title in title_values_for_scan(scan_row)
        ),
        default=0,
    )


def newer_arxiv_version(local_id: str | None, zotero_id: str | None) -> bool:
    if not local_id or not zotero_id or arxiv_base(local_id) != arxiv_base(zotero_id):
        return False
    local_version = arxiv_version(local_id)
    zotero_version = arxiv_version(zotero_id)
    return bool(local_version and zotero_version and local_version > zotero_version)


def resolved_path_string(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(Path(value).expanduser().resolve(strict=False))
    except Exception:
        return str(Path(value).expanduser().absolute())


def same_resolved_path(local_path: str, attachment_paths: list[str]) -> bool:
    local_resolved = resolved_path_string(local_path)
    for attachment_path in attachment_paths:
        attachment_resolved = resolved_path_string(attachment_path)
        if local_resolved and attachment_resolved and local_resolved == attachment_resolved:
            return True
        try:
            if local_path and attachment_path and Path(local_path).expanduser().samefile(Path(attachment_path).expanduser()):
                return True
        except Exception:
            continue
    return False


def local_duplicate_keys(scan_row: dict[str, Any]) -> list[tuple[str, str]]:
    detected = scan_row.get("detected", {})
    keys: list[tuple[str, str]] = []
    doi = normalize_doi(detected.get("doi"))
    if doi:
        keys.append(("doi", doi))
    base = arxiv_base(detected.get("arxiv_id"))
    if base:
        keys.append(("arxiv_base", base))
    sha = scan_row.get("sha256")
    if sha:
        keys.append(("sha256", str(sha)))
    return keys


def metadata_clarity_score(scan_row: dict[str, Any]) -> int:
    detected = scan_row.get("detected", {})
    score = 0
    if scan_row.get("scan_status") == "ok":
        score += 3
    if normalize_doi(detected.get("doi")):
        score += 4
    if detected.get("arxiv_id"):
        score += 4
    if detected.get("title"):
        score += 3
    if detected.get("year"):
        score += 2
    if detected.get("abstract_present") or scan_row.get("first_page_abstract_candidate"):
        score += 3
    if scan_row.get("pdf_metadata_author"):
        score += 1
    if scan_row.get("page_count"):
        score += 1
    if not scan_row.get("errors"):
        score += 1
    return score


def modified_timestamp(scan_row: dict[str, Any]) -> float:
    value = scan_row.get("modified_at")
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except Exception:
        return 0.0


def canonical_local_sort_key(scan_row: dict[str, Any]) -> tuple[int, int, int, int, float]:
    detected = scan_row.get("detected", {})
    return (
        metadata_clarity_score(scan_row),
        arxiv_version(detected.get("arxiv_id")) or 0,
        int(scan_row.get("size_bytes") or 0),
        -len(resolved_path_string(scan_row.get("path"))),
        modified_timestamp(scan_row),
    )


def local_duplicate_groups(scan_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    parent = list(range(len(scan_rows)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    seen: dict[tuple[str, str], int] = {}
    for index, row in enumerate(scan_rows):
        for key in local_duplicate_keys(row):
            if key in seen:
                union(index, seen[key])
            else:
                seen[key] = index

    groups: dict[int, list[int]] = {}
    for index, row in enumerate(scan_rows):
        if not local_duplicate_keys(row):
            continue
        groups.setdefault(find(index), []).append(index)

    duplicates: dict[str, dict[str, Any]] = {}
    for group_indices in groups.values():
        if len(group_indices) < 2:
            continue
        canonical_index = max(group_indices, key=lambda idx: canonical_local_sort_key(scan_rows[idx]))
        canonical = scan_rows[canonical_index]
        canonical_path = canonical.get("path")
        canonical_keys = set(local_duplicate_keys(canonical))
        for index in group_indices:
            if index == canonical_index:
                continue
            row = scan_rows[index]
            shared = sorted({f"{kind}:{value}" for kind, value in canonical_keys & set(local_duplicate_keys(row))})
            duplicates[str(row.get("path"))] = {
                "canonical_local_path": canonical_path,
                "canonical_filename": canonical.get("filename"),
                "local_duplicate_reason": ", ".join(shared) or "same DOI/arXiv/hash as canonical local file",
                "canonical_selection": {
                    "metadata_clarity_score": metadata_clarity_score(canonical),
                    "arxiv_version": arxiv_version((canonical.get("detected") or {}).get("arxiv_id")),
                    "size_bytes": canonical.get("size_bytes"),
                    "modified_at": canonical.get("modified_at"),
                },
            }
    return duplicates


def match_scan_row(scan_row: dict[str, Any], zotero_items: list[dict[str, Any]]) -> dict[str, Any]:
    if scan_row.get("scan_status") != "ok":
        return {
            "local_path": scan_row.get("path"),
            "match_status": "error",
            "matched_zotero_item_key": None,
            "matched_zotero_title": None,
            "match_reason": "; ".join(scan_row.get("errors", [])) or "scan failed",
            "match_confidence": 0.0,
            "safe_to_import": False,
            "safe_to_replace_existing_pdf": False,
            "reading_work_present_on_existing": False,
        }
    detected = scan_row.get("detected", {})
    doi = normalize_doi(detected.get("doi"))
    arxiv_id = detected.get("arxiv_id")
    local_base = arxiv_base(arxiv_id)
    normalized_titles = [normalize_title_v3(title) for title in title_values_for_scan(scan_row)]
    local_year = detected.get("year")
    local_author = local_first_author(scan_row)
    local_path = str(scan_row.get("path") or "")
    local_sha = scan_row.get("sha256")
    best_possible: tuple[float, dict[str, Any], str] | None = None

    for item in zotero_items:
        item_arxiv_base = item.get("arxiv_base_id") or arxiv_base(item.get("arxiv_id"))
        if doi and doi == item.get("doi_normalized"):
            return match_result(scan_row, item, "exact_existing", "same DOI", 1.0)
        if local_base and local_base == item_arxiv_base:
            if newer_arxiv_version(arxiv_id, item.get("arxiv_id")):
                return match_result(scan_row, item, "update_candidate", "newer arXiv version", 0.97)
            return match_result(scan_row, item, "exact_existing", "same arXiv base ID", 0.98)
        if local_sha and local_sha in {sha for sha in item.get("attachment_sha256", []) if sha}:
            return match_result(scan_row, item, "exact_existing", "same PDF SHA256", 1.0)
        if same_resolved_path(local_path, item.get("attachment_paths", [])):
            return match_result(scan_row, item, "exact_existing", "same resolved attachment local path", 1.0)
        if (
            local_year
            and item.get("year") == local_year
            and local_author
            and local_author == item.get("first_author")
            and any(title and title == item.get("normalized_title") for title in normalized_titles)
        ):
            return match_result(scan_row, item, "exact_existing", "same normalized title, year, and first author", 0.99)

        same_title = any(title and title == item.get("normalized_title") for title in normalized_titles)
        if same_title:
            best_possible = max_match(best_possible, (0.95, item, "same normalized title; needs review"))
        similarity = best_title_similarity(scan_row, item)
        if similarity >= 90 and not (doi or arxiv_id):
            best_possible = max_match(best_possible, (similarity / 100, item, "fuzzy title >= 0.90 without DOI/arXiv"))
        elif similarity >= 96:
            best_possible = max_match(best_possible, (similarity / 100, item, "fuzzy title >= 0.96; needs review"))

    if best_possible:
        confidence, item, reason = best_possible
        return match_result(scan_row, item, "possible_existing", reason, confidence)
    return {
        "local_path": scan_row.get("path"),
        "match_status": "new",
        "matched_zotero_item_key": None,
        "matched_zotero_title": None,
        "match_reason": "no Zotero DOI, arXiv, path, hash, or title match",
        "match_confidence": 0.0,
        "safe_to_import": True,
        "safe_to_replace_existing_pdf": False,
        "reading_work_present_on_existing": False,
    }


def max_match(
    current: tuple[float, dict[str, Any], str] | None,
    candidate: tuple[float, dict[str, Any], str],
) -> tuple[float, dict[str, Any], str]:
    if current is None or candidate[0] > current[0]:
        return candidate
    return current


def year_close(left: int | None, right: int | None) -> bool:
    if left is None or right is None:
        return True
    return abs(int(left) - int(right)) <= 1


def match_result(
    scan_row: dict[str, Any],
    item: dict[str, Any],
    status: str,
    reason: str,
    confidence: float,
) -> dict[str, Any]:
    reading_work = bool(item.get("reading_work_present"))
    detected = scan_row.get("detected", {})
    result = {
        "local_path": scan_row.get("path"),
        "match_status": status,
        "matched_zotero_item_key": item.get("item_key"),
        "matched_zotero_title": item.get("title"),
        "match_reason": reason,
        "match_confidence": round(confidence, 3),
        "safe_to_import": status == "new",
        "safe_to_replace_existing_pdf": False,
        "reading_work_present_on_existing": reading_work,
        "unsafe_auto_replace": reading_work,
    }
    if status == "update_candidate":
        result.update(
            {
                "existing_arxiv_id": item.get("arxiv_id"),
                "local_arxiv_id": detected.get("arxiv_id"),
                "existing_version": arxiv_version(item.get("arxiv_id")),
                "local_version": arxiv_version(detected.get("arxiv_id")),
                "suggested_action": "attach new version or replace linked PDF after review",
                "safe_to_replace_existing_pdf": not reading_work,
            }
        )
    return result


def local_duplicate_match_result(scan_row: dict[str, Any], duplicate: dict[str, Any]) -> dict[str, Any]:
    return {
        "local_path": scan_row.get("path"),
        "match_status": "local_duplicate",
        "matched_zotero_item_key": None,
        "matched_zotero_title": None,
        "match_reason": duplicate.get("local_duplicate_reason") or "duplicate local file",
        "match_confidence": 1.0,
        "safe_to_import": False,
        "safe_to_replace_existing_pdf": False,
        "reading_work_present_on_existing": False,
        "unsafe_auto_replace": False,
        "canonical_local_path": duplicate.get("canonical_local_path"),
        "canonical_filename": duplicate.get("canonical_filename"),
        "canonical_selection": duplicate.get("canonical_selection", {}),
    }


def match_local_to_zotero(scan: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    rows = list(scan.get("files", []))
    local_duplicates = local_duplicate_groups(rows)
    matches = [
        local_duplicate_match_result(row, local_duplicates[str(row.get("path"))])
        if str(row.get("path")) in local_duplicates
        else match_scan_row(row, index.get("items", []))
        for row in rows
    ]
    return {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "local_scan": "data/local_scan.json",
        "zotero_index": "data/zotero_index.json",
        "matches": matches,
    }


def write_match_report(plan: dict[str, Any], path: Path) -> None:
    ensure_parent_dir(path)
    rows = plan.get("matches", [])
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["match_status"]] = counts.get(row["match_status"], 0) + 1
    lines = ["# local zotero match report", ""]
    lines.extend(f"- {key}: {value}" for key, value in sorted(counts.items()))
    lines.extend(["", "## Matches", ""])
    for row in rows:
        lines.append(
            f"- {row['match_status']}: `{row['local_path']}` -> "
            f"{row.get('matched_zotero_item_key') or 'none'} ({row['match_reason']})"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def classify_text(row: dict[str, Any]) -> str:
    detected = row.get("detected", {})
    return " ".join(
        str(value or "")
        for value in [
            detected.get("title"),
            detected.get("doi"),
            detected.get("arxiv_id"),
            row.get("filename"),
            row.get("pdf_metadata_title"),
            row.get("first_page_abstract_candidate"),
            row.get("first_pages_text"),
        ]
    ).lower()


def _clean_text(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value if item)
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _text_before_references(text: str) -> str:
    match = re.search(r"(?is)(?:^|\n|\.\s+)\s*(?:references|bibliography)\s*(?:\n|$|[:.]|\s)", text)
    return text[: match.start()] if match else text


def _keyword_text(row: dict[str, Any]) -> str:
    text = row.get("first_pages_text") or ""
    match = re.search(r"(?is)\bkeywords?\b\s*[:.\-]?\s+(?P<body>.+?)(?=\n\s*(?:abstract|1\s+introduction|introduction)\b|$)", text)
    return _clean_text(match.group("body")) if match else ""


def classification_evidence(row: dict[str, Any]) -> dict[str, Any]:
    detected = row.get("detected", {})
    title = _clean_text(detected.get("title") or row.get("pdf_metadata_title") or title_from_filename(Path(row.get("filename") or "")))
    abstract = _clean_text(
        row.get("first_page_abstract_candidate")
        or detected.get("abstract")
        or detected.get("abstractNote")
        or row.get("abstract")
    )
    first_pages = _clean_text(row.get("first_pages_text"))
    arxiv_categories = _clean_text(row.get("arxiv_categories") or detected.get("arxiv_categories"))
    venue = _clean_text(row.get("publicationTitle") or row.get("venue") or detected.get("publicationTitle"))
    existing_tags = _clean_text(row.get("existing_tags") or detected.get("existing_tags"))
    values = [
        title,
        abstract,
        arxiv_categories,
        venue,
        _clean_text(detected.get("doi")),
        _clean_text(detected.get("arxiv_id")),
        _clean_text(row.get("filename")),
        _clean_text(row.get("pdf_metadata_title")),
        _keyword_text(row),
        first_pages,
        existing_tags,
    ]
    full_text = "\n".join(value for value in values if value)
    main_text = _text_before_references(full_text).lower()
    return {
        "title": title,
        "abstract": abstract,
        "first_pages_text": first_pages,
        "arxiv_categories": arxiv_categories,
        "venue": venue,
        "keywords": _keyword_text(row),
        "filename": _clean_text(row.get("filename")),
        "existing_tags": existing_tags,
        "full_text": full_text.lower(),
        "main_text": main_text,
        "detected": detected,
    }


def _contains_any(text: str, terms: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    for term in terms:
        pattern = r"(?<![a-z0-9])" + re.escape(term.lower()).replace(r"\ ", r"[\s\-]+") + r"(?![a-z0-9])"
        if re.search(pattern, text):
            matches.append(term)
    return matches


def _evidence_snippet(text: str, term: str) -> str:
    if not text or not term:
        return ""
    normalized = re.sub(r"\s+", " ", text)
    index = normalized.lower().find(term.lower())
    if index < 0:
        return term
    start = max(0, index - 70)
    end = min(len(normalized), index + len(term) + 90)
    prefix = "..." if start else ""
    suffix = "..." if end < len(normalized) else ""
    return f"{prefix}{normalized[start:end].strip()}{suffix}"


def _add_candidate(
    candidates: list[dict[str, Any]],
    collection: str,
    score: float,
    tags: list[str],
    reason: str,
    evidence_text: str,
    matched: list[str],
) -> None:
    if not matched:
        return
    candidates.append(
        {
            "collection": collection,
            "score": score,
            "tags": tags,
            "reason": reason,
            "matched_terms": matched,
            "evidence_snippet": _evidence_snippet(evidence_text, matched[0]),
        }
    )


def _trusted_arxiv_source(row: dict[str, Any], evidence: dict[str, Any]) -> bool:
    detected = row.get("detected", {})
    doi = normalize_doi(detected.get("doi"))
    text = evidence["full_text"]
    return bool(
        arxiv_id_from_doi(doi)
        or arxiv_id_from_url(text)
        or re.search(r"(?i)\barxiv\s*:\s*\d{2}(?:0[1-9]|1[0-2])\.\d{4,5}(?:v\d+)?", text)
    )


def _source_tag(row: dict[str, Any], evidence: dict[str, Any]) -> str:
    detected = row.get("detected", {})
    doi = normalize_doi(detected.get("doi"))
    text = evidence["full_text"]
    if detected.get("arxiv_id") and _trusted_arxiv_source(row, evidence):
        return "source/arxiv"
    if doi and doi.startswith(("10.1109/", "10.1145/")):
        return "source/conference"
    if doi and doi.startswith(("10.1016/", "10.1038/", "10.1007/", "10.3390/", "10.1039/", "10.1088/")):
        return "source/journal"
    if "workshop" in text:
        return "source/workshop"
    if detected.get("arxiv_id"):
        return "source/local-pdf"
    return "source/local-pdf"


def _metadata_missing(row: dict[str, Any], evidence: dict[str, Any]) -> bool:
    detected = row.get("detected", {})
    return not (detected.get("doi") or detected.get("arxiv_id")) or not evidence["title"] or not detected.get("year")


def _abstract_missing(row: dict[str, Any], evidence: dict[str, Any]) -> bool:
    detected = row.get("detected", {})
    return not bool(detected.get("abstract_present") or evidence["abstract"])


def _resource_candidates(candidates: list[dict[str, Any]], evidence: dict[str, Any]) -> None:
    text = evidence["main_text"]
    survey_terms = ("survey", "review", "tutorial")
    dataset_terms = ("introduce a dataset", "new dataset", "dataset", "corpus")
    benchmark_terms = ("benchmark", "leaderboard", "evaluation suite", "challenge", "evaluation protocol")
    tool_terms = ("toolbox", "toolkit", "software framework", "platform", "open-source library", "reusable pipeline")
    foundational_terms = (
        "attention is all you need",
        "deep residual learning",
        "batch normalization",
        "you only look once",
        "faster r-cnn",
        "feature pyramid networks",
        "u-net",
        "an image is worth 16x16 words",
        "learning transferable visual models",
        "neural ordinary differential equations",
        "semi-supervised classification with graph convolutional networks",
        "a simple framework for contrastive learning",
        "momentum contrast",
        "fixmatch",
        "end-to-end object detection with transformers",
    )
    _add_candidate(
        candidates,
        "AI Library/30 Resources/Surveys",
        0.78,
        ["type/survey"],
        "survey/tutorial signal",
        text,
        _contains_any(text, survey_terms),
    )
    dataset_matches = _contains_any(text, dataset_terms)
    if dataset_matches and _contains_any(text, ("introduce", "propose", "present", "release", "construct", "curate")):
        _add_candidate(
            candidates,
            "AI Library/30 Resources/Datasets",
            0.72,
            ["type/dataset"],
            "paper appears to introduce a dataset",
            text,
            dataset_matches,
        )
    benchmark_matches = _contains_any(text, benchmark_terms)
    if benchmark_matches and _contains_any(text, ("introduce", "propose", "present", "evaluate", "evaluation suite", "leaderboard")):
        _add_candidate(
            candidates,
            "AI Library/30 Resources/Benchmarks",
            0.72,
            ["type/benchmark"],
            "paper appears to introduce a benchmark or evaluation protocol",
            text,
            benchmark_matches,
        )
    _add_candidate(
        candidates,
        "AI Library/30 Resources/Toolkits & Libraries",
        0.72,
        ["type/system"],
        "paper appears to introduce software/tooling",
        text,
        _contains_any(text, tool_terms),
    )
    _add_candidate(
        candidates,
        "AI Library/30 Resources/Foundational Papers",
        0.86,
        ["type/foundational"],
        "foundational paper title or canonical method signal",
        text,
        _contains_any(text, foundational_terms),
    )


def classify_scan_row(row: dict[str, Any], forced_review: str | None = None) -> dict[str, Any]:
    evidence = classification_evidence(row)
    if forced_review:
        review_collection = (
            NEW_ARXIV_VERSION_COLLECTION
            if forced_review == "update_candidate"
            else POSSIBLE_ZOTERO_DUPLICATE_COLLECTION
        )
        return {
            "target_collections": [review_collection],
            "normalized_tags": clamp_tags_v3(
                [
                    "status/review-needed",
                    "cleanup/new-version" if forced_review == "update_candidate" else "cleanup/possible-existing",
                    _source_tag(row, evidence),
                ]
            ),
            "confidence": 0.2,
            "rationale": f"sent to review because match_status={forced_review}",
            "evidence_snippets": [],
        }

    text = evidence["main_text"]
    title = evidence["title"].lower()
    abstract = evidence["abstract"].lower()
    candidates: list[dict[str, Any]] = []
    tags = ["status/to-read", _source_tag(row, evidence), "type/method"]

    candidates.extend(override_candidates_for_evidence(evidence))

    if "looped world models" in title or "first looped architectures for world modelling" in abstract:
        candidates.extend(
            [
                {
                    "collection": "AI Library/20 Areas/World Models & Simulation/Latent World Models",
                    "score": 0.97,
                    "tags": ["area/world-models", "method/world-model", "task/world-simulation"],
                    "reason": "Looped World Models special rule",
                    "matched_terms": ["Looped World Models"],
                    "evidence_snippet": _evidence_snippet(evidence["full_text"], "Looped World Models"),
                },
                {
                    "collection": "AI Library/20 Areas/Recurrent & Adaptive Computation/Looped Transformers",
                    "score": 0.91,
                    "tags": [
                        "area/recurrent-adaptive-computation",
                        "method/looped-transformer",
                        "method/recurrent-depth",
                        "method/adaptive-computation",
                    ],
                    "reason": "looped/recurrent-depth architecture signal",
                    "matched_terms": ["looped"],
                    "evidence_snippet": _evidence_snippet(evidence["full_text"], "looped"),
                },
                {
                    "collection": "AI Library/20 Areas/Efficient ML Systems/Parameter Sharing",
                    "score": 0.86,
                    "tags": ["area/efficient-ml", "method/parameter-sharing", "method/transformer"],
                    "reason": "parameter-shared recurrent transformer signal",
                    "matched_terms": ["parameter"],
                    "evidence_snippet": _evidence_snippet(evidence["full_text"], "parameter"),
                },
            ]
        )

    if strict_rag_signal(text):
        _add_candidate(
            candidates,
            "AI Library/20 Areas/LLMs & Reasoning/RAG & Retrieval",
            0.88,
            ["area/llm", "method/rag", "method/retrieval"],
            "explicit RAG/retrieval evidence outside references",
            text,
            _contains_any(
                text,
                (
                    "retrieval augmented generation",
                    "retrieval-augmented generation",
                    "retriever",
                    "dense retrieval",
                    "sparse retrieval",
                    "document retrieval",
                    "passage retrieval",
                    "query-document matching",
                    "query-document retrieval",
                    "vector index",
                    "knowledge base retrieval",
                    "knowledge-base retrieval",
                    "grounded generation",
                    "citation-grounded generation",
                    "retrieve-then-generate",
                ),
            ),
        )

    _add_candidate(
        candidates,
        "AI Library/20 Areas/World Models & Simulation/Latent World Models",
        0.86,
        ["area/world-models", "method/world-model", "task/world-simulation"],
        "world model / learned environment dynamics signal",
        text,
        _contains_any(
            text,
            (
                "world model",
                "environment dynamics",
                "latent dynamics",
                "model-based reinforcement learning",
                "learned simulator",
                "long-horizon rollout",
                "action-conditioned prediction",
                "future state prediction",
                "imagination rollout",
                "dreamer",
                "planet",
                "muzero",
                "genie",
                "sora as world model",
                "video world model",
            ),
        ),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/World Models & Simulation/Deferred Decoding",
        0.84,
        ["area/world-models", "method/world-model", "method/deferred-decoding"],
        "deferred decoding world-model signal",
        text,
        _contains_any(text, ("deferred decoding",)),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Recurrent & Adaptive Computation/Looped Transformers",
        0.82,
        ["area/recurrent-adaptive-computation", "method/looped-transformer", "method/transformer"],
        "looped transformer signal",
        text,
        _contains_any(text, ("looped transformer",)),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Recurrent & Adaptive Computation/Recurrent-Depth Models",
        0.82,
        ["area/recurrent-adaptive-computation", "method/recurrent-depth"],
        "recurrent-depth model signal",
        text,
        _contains_any(text, ("recurrent depth", "iterative latent depth")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Recurrent & Adaptive Computation/Adaptive Computation Time",
        0.8,
        ["area/recurrent-adaptive-computation", "method/adaptive-computation"],
        "adaptive computation signal",
        text,
        _contains_any(text, ("adaptive computation", "adaptive computation time", "test-time compute scaling")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Recurrent & Adaptive Computation/Early Exit",
        0.78,
        ["area/recurrent-adaptive-computation", "method/early-exit"],
        "early-exit/dynamic-depth signal",
        text,
        _contains_any(text, ("early exit", "dynamic depth", "elastic depth", "universal transformer")),
    )

    battery_matches = _contains_any(
        text,
        (
            "lithium-ion battery",
            "battery degradation",
            "cycle life",
            "soh",
            "state of health",
            "rul",
            "remaining useful life",
            "fast charging",
            "thermal runaway",
            "battery lifetime",
            "battery prognosis",
        ),
    )
    if battery_matches:
        battery_collection = "AI Library/20 Areas/Battery ML & Prognostics/Battery Life Prediction"
        battery_tags = ["area/battery-ml", "task/battery-prognostics"]
        if _contains_any(text, ("rul", "remaining useful life", "soh", "state of health")):
            battery_collection = "AI Library/20 Areas/Battery ML & Prognostics/RUL & SOH Estimation"
            battery_tags.extend(["task/rul-prediction", "task/soh-estimation"])
        elif _contains_any(text, ("degradation", "cycle life")):
            battery_collection = "AI Library/20 Areas/Battery ML & Prognostics/Degradation Modeling"
        elif _contains_any(text, ("fast charging",)):
            battery_collection = "AI Library/20 Areas/Battery ML & Prognostics/Fast Charging Optimization"
        elif _contains_any(text, ("thermal runaway", "failure", "safety")):
            battery_collection = "AI Library/20 Areas/Battery ML & Prognostics/Thermal Runaway & Safety"
            battery_tags.append("task/thermal-runaway")
        if _contains_any(text, ("physics-informed", "physics informed")):
            battery_collection = "AI Library/20 Areas/Battery ML & Prognostics/Physics-Informed Battery Models"
            battery_tags.append("method/physics-informed")
        if _contains_any(text, ("battery dataset", "battery benchmark")):
            battery_collection = "AI Library/20 Areas/Battery ML & Prognostics/Battery Datasets"
            battery_tags.append("type/dataset")
        _add_candidate(
            candidates,
            battery_collection,
            0.88,
            battery_tags,
            "battery ML/prognostics signal",
            text,
            battery_matches,
        )

    _add_candidate(
        candidates,
        "AI Library/20 Areas/Vision-Language-Action & Robotics/Robot Manipulation",
        0.84,
        ["area/vla-robotics", "task/robot-manipulation", "method/control"],
        "robot manipulation / VLA signal",
        text,
        _contains_any(
            text,
            (
                "vision-language-action",
                "vla",
                "robot manipulation",
                "imitation learning",
                "inverse dynamics",
                "action model",
                "policy learning",
                "bimanual",
                "robot policy",
                "embodied agent",
                "libero",
                "openvla",
                "smolvla",
            ),
        ),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Vision-Language-Action & Robotics/Imitation Learning",
        0.8,
        ["area/vla-robotics", "task/imitation-learning"],
        "imitation learning signal",
        text,
        _contains_any(text, ("imitation learning",)),
    )

    vlm_matches = _contains_any(
        text,
        (
            "clip",
            "vision-language model",
            "vision language model",
            "vlm",
            "multimodal prompt learning",
            "visual question answering",
            "image-text",
            "text-aware visual",
        ),
    )
    if vlm_matches:
        vlm_collection = "AI Library/20 Areas/Vision-Language Models/CLIP-style Representation"
        vlm_tags = ["area/vlm", "task/multimodal-understanding"]
        if _contains_any(text, ("coop", "cocoop", "maple", "tip-adapter", "apollo", "graphadapter", "prompt learning", "adapter")):
            vlm_collection = "AI Library/20 Areas/Vision-Language Models/Prompt Learning & Adapters"
            vlm_tags.extend(["method/prompt-learning", "method/adapter"])
        elif _contains_any(text, ("visual question answering", "multimodal reasoning")):
            vlm_collection = "AI Library/20 Areas/Vision-Language Models/Multimodal Reasoning"
            vlm_tags.append("task/question-answering")
        elif _contains_any(text, ("vlm evaluation",)):
            vlm_collection = "AI Library/20 Areas/Vision-Language Models/VLM Evaluation"
        if "clip" in vlm_matches:
            vlm_tags.append("method/clip")
        _add_candidate(candidates, vlm_collection, 0.82, vlm_tags, "vision-language model signal", text, vlm_matches)

    anomaly_matches = _contains_any(
        text,
        (
            "anomaly detection",
            "defect detection",
            "industrial inspection",
            "mvtec",
            "crack segmentation",
            "fault detection",
            "zero-shot anomaly",
        ),
    )
    if anomaly_matches:
        anomaly_collection = "AI Library/20 Areas/Anomaly & Defect Detection/Industrial Anomaly Detection"
        anomaly_tags = ["area/anomaly-detection", "task/anomaly-detection"]
        if _contains_any(text, ("defect detection", "industrial inspection", "mvtec", "crack segmentation")):
            anomaly_collection = "AI Library/20 Areas/Anomaly & Defect Detection/Visual Defect Inspection"
            anomaly_tags.append("task/defect-inspection")
        if _contains_any(text, ("zero-shot anomaly", "anomalyclip", "winclip", "adaclip", "gpt-4v-ad")):
            anomaly_collection = "AI Library/20 Areas/Anomaly & Defect Detection/Zero-Shot Anomaly Detection"
            anomaly_tags.append("method/clip")
        if _contains_any(text, ("anomaly segmentation", "crack segmentation")):
            anomaly_collection = "AI Library/20 Areas/Anomaly & Defect Detection/Anomaly Segmentation"
            anomaly_tags.extend(["task/segmentation", "method/anomaly-localization"])
        _add_candidate(candidates, anomaly_collection, 0.84, anomaly_tags, "anomaly/defect detection signal", text, anomaly_matches)
        if _contains_any(text, ("anomalyclip", "winclip", "adaclip", "gpt-4v-ad", "vlm anomaly")):
            _add_candidate(
                candidates,
                "AI Library/20 Areas/Vision-Language Models/VLM Evaluation",
                0.72,
                ["area/vlm", "method/clip"],
                "VLM anomaly detection signal",
                text,
                _contains_any(text, ("anomalyclip", "winclip", "adaclip", "gpt-4v-ad", "vlm anomaly")),
            )

    _add_candidate(
        candidates,
        "AI Library/20 Areas/Computer Vision/Object Detection",
        0.8,
        ["area/classic-cv", "task/object-detection"],
        "object detection signal",
        text,
        _contains_any(text, ("yolo", "faster r-cnn", "detr", "object detection", "bounding box", "fpn")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Computer Vision/Segmentation",
        0.78,
        ["area/classic-cv", "task/segmentation"],
        "segmentation signal",
        text,
        _contains_any(text, ("segmentation", "u-net", "mask r-cnn", "sam")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Computer Vision/Vision Transformers",
        0.76,
        ["area/classic-cv", "method/vit", "method/transformer"],
        "vision transformer signal",
        text,
        _contains_any(text, ("vision transformer", "vit", "detr")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Computer Vision/CNN Architectures",
        0.75,
        ["area/classic-cv", "method/cnn"],
        "CNN architecture signal",
        text,
        _contains_any(text, ("resnet", "efficientnet", "eca-net", "senet", "cnn architecture", "convolutional neural network")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Computer Vision/Explainability & Attribution",
        0.76,
        ["area/classic-cv"],
        "explainability/attribution signal",
        text,
        _contains_any(text, ("grad-cam", "explainability", "attribution")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Computer Vision/State Space Vision Models",
        0.76,
        ["area/classic-cv", "method/state-space-model", "method/mamba"],
        "vision state-space model signal",
        text,
        _contains_any(text, ("mamba vision", "state space vision", "vision mamba")),
    )

    _add_candidate(
        candidates,
        "AI Library/20 Areas/Representation Learning/Contrastive Learning",
        0.84,
        ["area/representation-learning", "method/contrastive-learning"],
        "contrastive representation learning signal",
        text,
        _contains_any(text, ("simclr", "moco", "contrastive learning")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Representation Learning/Self-Supervised Learning",
        0.82,
        ["area/representation-learning", "method/self-supervised-learning"],
        "self-supervised representation learning signal",
        text,
        _contains_any(text, ("self-supervised", "self supervised")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Representation Learning/Semi-Supervised Learning",
        0.82,
        ["area/representation-learning", "method/semi-supervised-learning"],
        "semi-supervised representation learning signal",
        text,
        _contains_any(text, ("semi-supervised", "semi supervised", "fixmatch", "comatch", "simmatch")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Representation Learning/Data Augmentation",
        0.76,
        ["area/representation-learning", "method/data-augmentation"],
        "data augmentation signal",
        text,
        _contains_any(text, ("randaugment", "autoaugment", "data augmentation")),
    )

    _add_candidate(
        candidates,
        "AI Library/20 Areas/Graph Learning/GNN Architectures",
        0.82,
        ["area/graph-learning", "method/gnn"],
        "GNN/graph convolution signal",
        text,
        _contains_any(text, ("gcn", "gnn", "graph neural", "graph convolution")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Graph Learning/Knowledge Graphs",
        0.8,
        ["area/graph-learning", "method/knowledge-graph"],
        "knowledge graph signal",
        text,
        _contains_any(text, ("knowledge graph", "transe", "graph embedding")),
    )

    _add_candidate(
        candidates,
        "AI Library/20 Areas/Time-Series & Dynamical Systems/Neural ODEs & CDEs",
        0.84,
        ["area/time-series", "method/neural-ode", "method/neural-cde"],
        "Neural ODE/CDE signal",
        text,
        _contains_any(text, ("neural ode", "neural cde", "controlled differential equation", "controlled differential equations")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Time-Series & Dynamical Systems/Model Predictive Control",
        0.82,
        ["area/time-series", "method/mpc", "method/control"],
        "model predictive control signal",
        text,
        _contains_any(text, ("model predictive control", "mpc", "temporal difference control")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Time-Series & Dynamical Systems/State-Space Models",
        0.78,
        ["area/time-series", "method/state-space-model"],
        "state-space dynamics signal",
        text,
        _contains_any(text, ("state-space", "state space model", "state-space dynamics")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Time-Series & Dynamical Systems/Wavelets & Signal Processing",
        0.76,
        ["area/time-series"],
        "wavelet/signal processing signal",
        text,
        _contains_any(text, ("wavelet", "signal processing")),
    )

    _add_candidate(
        candidates,
        "AI Library/20 Areas/LLMs & Reasoning/KV Cache & Compression",
        0.84,
        ["area/llm", "area/efficient-ml", "method/kv-cache-compression"],
        "KV cache/compression signal",
        text,
        _contains_any(text, ("kv cache", "cache compression", "kv-cache compression")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Efficient ML Systems/Inference Acceleration",
        0.82,
        ["area/efficient-ml"],
        "efficient inference/acceleration signal",
        text,
        _contains_any(text, ("inference acceleration", "efficient inference", "edge deployment", "quantization", "pruning")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Efficient ML Systems/Distillation",
        0.8,
        ["area/efficient-ml", "method/distillation"],
        "distillation signal",
        text,
        _contains_any(text, ("distillation", "small lm", "small language model")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Efficient ML Systems/Parameter Sharing",
        0.78,
        ["area/efficient-ml", "method/parameter-sharing"],
        "parameter sharing signal",
        text,
        _contains_any(text, ("parameter sharing", "parameter-shared", "shared parameters")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/LLMs & Reasoning/Alignment & Safety",
        0.82,
        ["area/llm", "method/alignment"],
        "alignment/safety signal",
        text,
        _contains_any(text, ("alignment", "llm safety", "ai safety")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/LLMs & Reasoning/Hallucination & Factuality",
        0.8,
        ["area/llm"],
        "hallucination/factuality signal",
        text,
        _contains_any(text, ("hallucination", "factuality")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/LLMs & Reasoning/Jailbreaks & Security",
        0.8,
        ["area/llm", "method/jailbreak"],
        "jailbreak/security signal",
        text,
        _contains_any(text, ("jailbreak", "prompt injection", "llm security")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/LLMs & Reasoning/Chain-of-Thought & Latent Reasoning",
        0.78,
        ["area/llm", "method/cot", "method/latent-reasoning", "task/reasoning"],
        "chain-of-thought/latent reasoning signal",
        text,
        _contains_any(text, ("chain-of-thought", "chain of thought", "latent reasoning", "reasoning")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/LLMs & Reasoning/Prompting & In-Context Learning",
        0.76,
        ["area/llm", "method/prompting"],
        "prompting/in-context learning signal",
        text,
        _contains_any(text, ("prompting", "in-context learning", "in context learning")),
    )

    _add_candidate(
        candidates,
        "AI Library/20 Areas/Medical AI/Radiology VLMs",
        0.84,
        ["area/medical-ai", "area/vlm", "task/medical-diagnosis"],
        "radiology/biomedical VLM signal",
        text,
        _contains_any(text, ("chest x-ray", "chest x ray", "radiology", "biomedical vlm", "medical image-text", "medical vision-language")),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Medical AI/Medical Segmentation",
        0.8,
        ["area/medical-ai", "task/segmentation"],
        "medical segmentation signal",
        text,
        _contains_any(text, ("medical segmentation",)),
    )
    _add_candidate(
        candidates,
        "AI Library/20 Areas/Medical AI/Medical Diagnosis",
        0.8,
        ["area/medical-ai", "task/medical-diagnosis"],
        "medical diagnosis signal",
        text,
        _contains_any(text, ("medical diagnosis", "diagnosis")),
    )
    _resource_candidates(candidates, evidence)

    if "transformer" in text:
        tags.append("method/transformer")
    if "cnn" in text or "convolution" in text:
        tags.append("method/cnn")
    if "diffusion" in text:
        tags.append("method/diffusion")
    if "mamba" in text:
        tags.append("method/mamba")
    if "flow matching" in text:
        tags.append("method/flow-matching")

    sorted_candidates = sorted(candidates, key=lambda candidate: candidate["score"], reverse=True)
    collections = unique_preserve_order([candidate["collection"] for candidate in sorted_candidates])
    for candidate in sorted_candidates:
        tags.extend(candidate["tags"])
    confidence = round(sorted_candidates[0]["score"], 2) if sorted_candidates else 0.25
    reasons = [candidate["reason"] for candidate in sorted_candidates]
    if confidence >= 0.75:
        collections = collections[:3]
    elif confidence >= 0.55:
        collections = unique_preserve_order([collections[0], AMBIGUOUS_CLASSIFICATION_COLLECTION, *collections[1:2]])
        tags.append("status/review-needed")
        tags.append("cleanup/low-confidence")
    else:
        collections = [AMBIGUOUS_CLASSIFICATION_COLLECTION]
        tags.append("status/review-needed")
        tags.append("cleanup/low-confidence")
        confidence = 0.25
        reasons.append("no deterministic fine-grained taxonomy rule reached confidence threshold")

    if _metadata_missing(row, evidence):
        collections.append(MISSING_METADATA_REVIEW_COLLECTION)
        tags.append("cleanup/missing-metadata")
    if _abstract_missing(row, evidence):
        collections.append(MISSING_ABSTRACT_REVIEW_COLLECTION)
        tags.append("cleanup/missing-abstract")

    collections = unique_preserve_order(collections)
    return {
        "target_collections": collections,
        "normalized_tags": clamp_tags_v3(tags),
        "confidence": round(confidence, 2),
        "rationale": "; ".join(unique_preserve_order(reasons)),
        "evidence_snippets": [
            {
                "collection": candidate["collection"],
                "matched_terms": candidate["matched_terms"],
                "snippet": candidate["evidence_snippet"],
            }
            for candidate in sorted_candidates[:5]
        ],
    }


def strict_rag_signal(text: str) -> bool:
    non_reference_text = _text_before_references(text).lower()
    override_required_terms = rag_unless_contains_terms()
    if override_required_terms and not _contains_any(non_reference_text, override_required_terms):
        return False
    patterns = (
        "retrieval augmented generation",
        "retrieval-augmented generation",
        "retriever",
        "dense retrieval",
        "sparse retrieval",
        "document retrieval",
        "passage retrieval",
        "query-document matching",
        "query-document retrieval",
        "vector index",
        "knowledge-base retrieval",
        "knowledge base retrieval",
        "grounded generation",
        "citation-grounded",
        "citation-grounded generation",
        "retrieve-then-generate",
    )
    return any(pattern in non_reference_text for pattern in patterns)


def classify_new_local_papers(
    scan: dict[str, Any],
    matches: dict[str, Any],
    include_possible_existing: bool = False,
    include_update_candidates: bool = False,
    use_gemini: bool = False,
    gemini_model: str = DEFAULT_GEMINI_MODEL,
    gemini_batch_size: int = 5,
    stop_on_gemini_quota: bool = True,
    gemini_review_threshold: float = 0.75,
    gemini_client: GeminiClient | None = None,
) -> dict[str, Any]:
    match_by_path = {row["local_path"]: row for row in matches.get("matches", [])}
    items: list[dict[str, Any]] = []
    gemini_status: dict[str, Any] = {
        "enabled": use_gemini,
        "model": gemini_model if use_gemini else None,
        "batch_size": gemini_batch_size if use_gemini else None,
        "review_threshold": gemini_review_threshold if use_gemini else None,
        "stopped_due_to_quota": False,
        "errors": [],
    }
    owns_gemini = False
    gemini = gemini_client
    if use_gemini and gemini is None:
        gemini = GeminiClient(model=gemini_model)
        owns_gemini = True
    batch_size = max(1, gemini_batch_size)
    rows = list(scan.get("files", []))
    try:
        for batch_start in range(0, len(rows), batch_size):
            for row in rows[batch_start : batch_start + batch_size]:
                match = match_by_path.get(row.get("path"))
                status = match.get("match_status") if match else "new"
                if status in {"exact_existing", "likely_existing", "local_duplicate", "error"}:
                    continue
                if status == "possible_existing" and not include_possible_existing:
                    items.append(
                        build_classification_item(
                            row,
                            match,
                            classify_scan_row(row, "possible_existing"),
                            "review",
                        )
                    )
                    continue
                if status == "update_candidate" and not include_update_candidates:
                    items.append(
                        build_classification_item(
                            row,
                            match,
                            classify_scan_row(row, "update_candidate"),
                            "review",
                        )
                    )
                    continue
                if status == "new" or include_possible_existing or include_update_candidates:
                    classification = classify_scan_row(row)
                    if use_gemini and gemini is not None and should_try_gemini_classification(classification):
                        gemini_result = classify_with_gemini(
                            classification_evidence(row),
                            gemini,
                            review_threshold=gemini_review_threshold,
                        )
                        error_type = gemini_result.get("error_type")
                        if error_type:
                            gemini_status["errors"].append(
                                {
                                    "local_path": row.get("path"),
                                    "error_type": error_type,
                                    "message": gemini_result["classification"]["rationale"],
                                }
                            )
                        classification = merge_gemini_fallback_classification(
                            deterministic=classification,
                            gemini_classification=gemini_result["classification"],
                            accepted=bool(gemini_result.get("ok")),
                        )
                        if error_type == "rate_limited" and stop_on_gemini_quota:
                            gemini_status["stopped_due_to_quota"] = True
                            items.append(build_classification_item(row, match, classification, "review"))
                            raise GeminiBatchStopped
                    items.append(build_classification_item(row, match, classification, "import"))
    except GeminiBatchStopped:
        pass
    finally:
        if owns_gemini and gemini is not None:
            gemini.close()
    return {
        "schema_version": "1.0",
        "taxonomy_version": "3.0",
        "generated_at": utc_now(),
        "collection_tree": COLLECTION_TREE_V3,
        "tag_vocabulary": TAG_VOCABULARY_V3,
        "classification_engine": "deterministic+gemini-fallback" if use_gemini else "deterministic",
        "partial": bool(gemini_status["stopped_due_to_quota"]),
        "gemini": gemini_status,
        "items": items,
    }


class GeminiBatchStopped(Exception):
    pass


def should_try_gemini_classification(classification: dict[str, Any]) -> bool:
    return (
        classification.get("confidence", 0) < 0.75
        or AMBIGUOUS_CLASSIFICATION_COLLECTION in classification.get("target_collections", [])
    )


def merge_gemini_fallback_classification(
    deterministic: dict[str, Any],
    gemini_classification: dict[str, Any],
    accepted: bool,
) -> dict[str, Any]:
    if accepted:
        merged = dict(gemini_classification)
        merged["rationale"] = (
            f"{gemini_classification.get('rationale', '')}; "
            f"deterministic fallback reason: {deterministic.get('rationale', '')}"
        ).strip("; ")
        return merged
    merged = dict(deterministic)
    merged["gemini_used"] = False
    merged["gemini_rejected"] = True
    merged["gemini_rejection_reason"] = gemini_classification.get("gemini_rejection_reason") or gemini_classification.get("rationale")
    merged["rationale"] = (
        f"{deterministic.get('rationale', '')}; Gemini fallback rejected: "
        f"{merged['gemini_rejection_reason']}"
    ).strip("; ")
    return merged


def build_classification_item(
    scan_row: dict[str, Any],
    match: dict[str, Any] | None,
    classification: dict[str, Any],
    action: str,
) -> dict[str, Any]:
    detected = scan_row.get("detected", {})
    return {
        "local_path": scan_row.get("path"),
        "filename": scan_row.get("filename"),
        "sha256": scan_row.get("sha256"),
        "sha256_first_1mb": scan_row.get("sha256_first_1mb"),
        "title": detected.get("title") or title_from_filename(Path(scan_row.get("filename") or "paper.pdf")),
        "year": detected.get("year"),
        "doi": detected.get("doi"),
        "arxiv_id": detected.get("arxiv_id"),
        "abstract_present": detected.get("abstract_present", False),
        "first_page_abstract_candidate": scan_row.get("first_page_abstract_candidate"),
        "match_status": match.get("match_status") if match else "new",
        "matched_zotero_item_key": match.get("matched_zotero_item_key") if match else None,
        "target_collections": classification["target_collections"],
        "normalized_tags": classification["normalized_tags"],
        "confidence": classification["confidence"],
        "rationale": classification["rationale"],
        "evidence_snippets": classification.get("evidence_snippets", []),
        "gemini_used": bool(classification.get("gemini_used")),
        "gemini_rejected": bool(classification.get("gemini_rejected")),
        "gemini_rejection_reason": classification.get("gemini_rejection_reason"),
        "classification_action": action,
    }


def write_classification_report(plan: dict[str, Any], markdown_output: Path, csv_output: Path) -> None:
    ensure_parent_dir(markdown_output)
    rows = plan.get("items", [])
    imports = sum(1 for row in rows if row.get("classification_action") == "import")
    review = sum(1 for row in rows if row.get("classification_action") == "review")
    lines = [
        "# local classification report",
        "",
        f"- Items: {len(rows)}",
        f"- Planned import: {imports}",
        f"- Review queue: {review}",
        f"- Classification engine: {plan.get('classification_engine', 'deterministic')}",
        f"- Gemini enabled: {str((plan.get('gemini') or {}).get('enabled', False)).lower()}",
        f"- Partial due to Gemini quota: {str(plan.get('partial', False)).lower()}",
        "",
        "## Items",
        "",
    ]
    for row in rows:
        lines.append(
            f"- {row['classification_action']}: `{row['local_path']}` -> "
            f"{'; '.join(row['target_collections'])} ({row['confidence']})"
        )
    markdown_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ensure_parent_dir(csv_output)
    pd.DataFrame(
        [
            {
                "local_path": row.get("local_path"),
                "title": row.get("title"),
                "year": row.get("year"),
                "doi": row.get("doi"),
                "arxiv_id": row.get("arxiv_id"),
                "action": row.get("classification_action"),
                "target_collections": "; ".join(row.get("target_collections", [])),
                "tags": "; ".join(row.get("normalized_tags", [])),
                "confidence": row.get("confidence"),
                "gemini_used": row.get("gemini_used", False),
                "gemini_rejected": row.get("gemini_rejected", False),
            }
            for row in rows
        ]
    ).to_csv(csv_output, index=False)


def identifier_for_item(item: dict[str, Any]) -> str:
    if item.get("arxiv_id"):
        return f"arXiv {item['arxiv_id']}"
    if item.get("doi"):
        return item["doi"]
    return f"local {str(item.get('sha256') or item.get('sha256_first_1mb') or 'unknown')[:8]}"


def plan_local_import(
    classification: dict[str, Any],
    vault_library: Path = DEFAULT_VAULT_LIBRARY,
) -> dict[str, Any]:
    seen: set[Path] = set()
    items: list[dict[str, Any]] = []
    for item in classification.get("items", []):
        if item.get("classification_action") != "import":
            continue
        source = Path(item["local_path"]).expanduser()
        year = item.get("year") or "unknown-year"
        primary = item.get("target_collections", [REVIEW_QUEUE_COLLECTION])[0]
        area = area_slug_from_collection(primary)
        filename = safe_pdf_filename(item.get("year"), item.get("title"), identifier_for_item(item))
        target = vault_library.expanduser() / area / str(year) / filename
        if target in seen or target.exists():
            target = target.with_name(f"{target.stem} [{str(item.get('sha256') or item.get('sha256_first_1mb'))[:8]}]{target.suffix}")
        seen.add(target)
        items.append(
            {
                "source_path": str(source),
                "planned_vault_path": str(target),
                "planned_filename": target.name,
                "planned_zotero_operation": "create",
                "planned_collections": item.get("target_collections", []),
                "planned_tags": unique_preserve_order([*item.get("normalized_tags", []), "paperflow/source-local-import"]),
                "metadata": {
                    "title": item.get("title"),
                    "year": item.get("year"),
                    "doi": item.get("doi"),
                    "arxiv_id": item.get("arxiv_id"),
                    "abstract_present": item.get("abstract_present", False),
                    "abstract": item.get("first_page_abstract_candidate"),
                },
                "classification": {
                    "rationale": item.get("rationale"),
                    "confidence": item.get("confidence"),
                },
                "gemini_used": item.get("gemini_used", False),
                "sha256": item.get("sha256"),
                "sha256_first_1mb": item.get("sha256_first_1mb"),
                "upload_to_zotero_storage": False,
                "actions": [
                    {"name": "copy_to_vault", "executed": False},
                    {"name": "create_or_update_zotero_item", "executed": False},
                    {"name": "create_linked_attachment", "executed": False},
                    {"name": "add_to_collections", "executed": False},
                    {"name": "add_tags", "executed": False},
                    {"name": "write_provenance", "executed": False},
                ],
            }
        )
    return {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "mode": "dry-run",
        "vault_library": str(vault_library.expanduser()),
        "storage_mode": "linked-local",
        "upload_to_zotero_storage": False,
        "items": items,
    }


def write_import_plan_report(plan: dict[str, Any], output_path: Path) -> None:
    ensure_parent_dir(output_path)
    lines = [
        "# local import plan",
        "",
        f"- Items: {len(plan.get('items', []))}",
        f"- Vault: `{plan.get('vault_library')}`",
        "- Mode: dry-run",
        "- Upload to Zotero Storage: false",
        "",
    ]
    for item in plan.get("items", []):
        lines.append(f"- `{item['source_path']}` -> `{item['planned_vault_path']}`")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_local_apply(apply: bool, confirm: str | None, user_id: str | None, api_key: str | None) -> None:
    if not apply:
        raise ValueError("apply-import is dry-run by default; pass --apply to write.")
    if confirm != LOCAL_IMPORT_CONFIRMATION:
        raise ValueError(f'confirmation must be exactly "{LOCAL_IMPORT_CONFIRMATION}"')
    if not user_id or not api_key:
        raise ValueError("ZOTERO_USER_ID and ZOTERO_API_KEY must be set.")
    if not user_id.isdigit():
        raise ValueError("ZOTERO_USER_ID must be numeric.")


def parent_body_for_local_import(item: dict[str, Any], collection_keys: list[str]) -> dict[str, Any]:
    metadata = item.get("metadata", {})
    extra_lines = [
        f"PaperFlow Source Path: {item.get('source_path')}",
        f"PaperFlow Import Time: {utc_now()}",
    ]
    if item.get("sha256"):
        extra_lines.append(f"PaperFlow PDF SHA256: {item['sha256']}")
    body: dict[str, Any] = {
        "itemType": "journalArticle",
        "title": metadata.get("title") or Path(item.get("source_path", "paper.pdf")).stem,
        "collections": collection_keys,
        "tags": [{"tag": tag} for tag in item.get("planned_tags", [])],
        "extra": "\n".join(extra_lines),
    }
    if metadata.get("doi"):
        body["DOI"] = metadata["doi"]
    if metadata.get("year"):
        body["date"] = str(metadata["year"])
    if metadata.get("arxiv_id"):
        body["url"] = f"https://arxiv.org/abs/{metadata['arxiv_id']}"
    if metadata.get("abstract"):
        body["abstractNote"] = metadata["abstract"]
    return body


def apply_local_import_plan(
    plan: dict[str, Any],
    user_id: str,
    api_key: str,
    web_base_url: str = "https://api.zotero.org",
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    plan["mode"] = "apply"
    with ZoteroWebClient(user_id=user_id, api_key=api_key, base_url=web_base_url) as client:
        collection_paths = list(
            dict.fromkeys(
                path
                for item in plan.get("items", [])
                for path in item.get("planned_collections", [])
            )
        )
        collections = client.iter_collections()
        key_by_path, _, _ = collection_maps(collections)
        for collection in creation_plan(collection_paths, collections):
            parent_path = collection["parentPath"]
            parent_key = key_by_path.get(parent_path) if parent_path else False
            response = client.post_collections([{"name": collection["name"], "parentCollection": parent_key}])
            events.append({"event": "collection-created", "path": collection["path"], "statusCode": response.status_code})
            collections = client.iter_collections()
            key_by_path, _, _ = collection_maps(collections)

        for item in plan.get("items", []):
            source = Path(item["source_path"]).expanduser()
            target = Path(item["planned_vault_path"]).expanduser()
            checksum = copy_pdf_to_vault(source, target, item.get("sha256"))
            mark_action(item, "copy_to_vault", True, target_path=str(target), sha256=checksum)
            events.append({"event": "pdf-copied-to-vault", "sourcePath": str(source), "targetPath": str(target)})

            collection_keys = [key_by_path[path] for path in item.get("planned_collections", []) if path in key_by_path]
            parent_body = parent_body_for_local_import(item, collection_keys)
            pseudo = {
                "doi_normalized": item.get("metadata", {}).get("doi"),
                "arxiv_id": item.get("metadata", {}).get("arxiv_id"),
            }
            parent_key = _find_existing_parent(client, pseudo)
            operation = "update" if parent_key else "create"
            if parent_key:
                response = client.patch_item(parent_key, parent_body)
            else:
                response = client.post_items([parent_body])
                parent_key = _created_key(response.json())
            mark_action(item, "create_or_update_zotero_item", True, item_key=parent_key)
            mark_action(item, "add_to_collections", True, collection_keys=collection_keys)
            mark_action(item, "add_tags", True, tags=item.get("planned_tags", []))
            mark_action(item, "write_provenance", True)
            events.append({"event": f"parent-item-{operation}", "itemKey": parent_key, "statusCode": response.status_code})

            response = client.post_items(
                [
                    linked_attachment_body(
                        parent_key,
                        target,
                        title=item.get("metadata", {}).get("title"),
                        vault_library=Path(plan["vault_library"]).expanduser(),
                    )
                ]
            )
            attachment_key = _created_key(response.json())
            mark_action(item, "create_linked_attachment", True, attachment_key=attachment_key, linked_pdf_path=str(target))
            item["zotero"] = {
                "operation": operation,
                "item_key": parent_key,
                "open_uri": _zotero_open_uri(parent_key),
                "write_executed": True,
            }
            item["final_linked_pdf_path"] = str(target)
            item["final_collections"] = item.get("planned_collections", [])
            item["final_tags"] = item.get("planned_tags", [])
            item["final_collection_keys"] = collection_keys
            events.append(
                {
                    "event": "linked-attachment-created",
                    "parentItemKey": parent_key,
                    "attachmentKey": attachment_key,
                    "path": str(target),
                    "statusCode": response.status_code,
                }
            )

    return {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "mode": "apply",
        "storage_mode": "linked-local",
        "upload_to_zotero_storage": False,
        "items": plan.get("items", []),
        "events": events,
    }


def mark_action(item: dict[str, Any], name: str, executed: bool, **extra: Any) -> None:
    for action in item.setdefault("actions", []):
        if action.get("name") == name:
            action["executed"] = executed
            action.update(extra)
            return
    item["actions"].append({"name": name, "executed": executed, **extra})


def timestamped_path(prefix: str, suffix: str = ".json", data_dir: Path = Path("data")) -> Path:
    return data_dir / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix}"


def write_local_apply_markdown(log: dict[str, Any], output_path: Path) -> None:
    ensure_parent_dir(output_path)
    lines = ["# local import apply log", "", f"- Items: {len(log.get('items', []))}", ""]
    for item in log.get("items", []):
        lines.append(f"- {item.get('zotero', {}).get('item_key')}: `{item.get('final_linked_pdf_path')}`")
    lines.extend(["", "## Events", ""])
    lines.extend(f"- {event}" for event in log.get("events", []))
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def latest_file(data_dir: Path, prefix: str, suffix: str = ".json") -> Path | None:
    if not data_dir.exists():
        return None
    files = [path for path in data_dir.iterdir() if path.name.startswith(prefix) and path.name.endswith(suffix)]
    return max(files, key=lambda path: path.stat().st_mtime) if files else None


def audit_local_import(
    plan_path: Path,
    apply_log_path: Path | None = None,
    data_dir: Path = Path("data"),
) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if apply_log_path is None:
        apply_log_path = latest_file(data_dir, "local_import_apply_log_")
    apply_log = json.loads(apply_log_path.read_text(encoding="utf-8")) if apply_log_path and apply_log_path.exists() else {}
    applied_by_source = {item.get("source_path"): item for item in apply_log.get("items", [])}
    rows = []
    for item in plan.get("items", []):
        applied = applied_by_source.get(item.get("source_path"), item)
        vault_path = Path(applied.get("final_linked_pdf_path") or applied.get("planned_vault_path", "")).expanduser()
        source = Path(item.get("source_path", "")).expanduser()
        actions = {action.get("name"): action for action in applied.get("actions", [])}
        row = {
            "source_path": str(source),
            "vault_path": str(vault_path),
            "vault_pdf_exists": vault_path.exists(),
            "source_file_exists": source.exists(),
            "zotero_item_key": applied.get("zotero", {}).get("item_key"),
            "zotero_write_executed": bool(applied.get("zotero", {}).get("write_executed")),
            "linked_attachment_created": bool(actions.get("create_linked_attachment", {}).get("executed")),
            "upload_to_zotero_storage": bool(applied.get("upload_to_zotero_storage", False)),
            "collections_match_plan": set(applied.get("final_collections", applied.get("planned_collections", []))) == set(item.get("planned_collections", [])),
            "tags_match_plan": set(applied.get("final_tags", applied.get("planned_tags", []))) >= set(item.get("planned_tags", [])),
        }
        row["audit_passed"] = (
            row["vault_pdf_exists"]
            and row["zotero_write_executed"]
            and row["linked_attachment_created"]
            and not row["upload_to_zotero_storage"]
            and row["collections_match_plan"]
            and row["tags_match_plan"]
        )
        rows.append(row)
    return {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "plan_path": str(plan_path),
        "apply_log_path": str(apply_log_path) if apply_log_path else None,
        "items": rows,
        "passed": all(row["audit_passed"] for row in rows) if rows else False,
    }


def write_local_audit_report(audit: dict[str, Any], path: Path) -> None:
    ensure_parent_dir(path)
    lines = ["# local import audit", "", f"- Passed: {audit.get('passed')}", ""]
    for row in audit.get("items", []):
        lines.append(f"- {row['audit_passed']}: `{row['source_path']}` -> `{row['vault_path']}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_source_cleanup(apply: bool, confirm: str | None, audit: dict[str, Any]) -> None:
    if not apply:
        return
    if confirm != SOURCE_QUARANTINE_CONFIRMATION:
        raise ValueError(f'confirmation must be exactly "{SOURCE_QUARANTINE_CONFIRMATION}"')
    if not audit.get("passed"):
        raise ValueError("import audit did not pass; refusing source-file cleanup")


def cleanup_source_files(
    audit: dict[str, Any],
    apply: bool = False,
    quarantine_root: Path | None = None,
) -> dict[str, Any]:
    quarantine_root = quarantine_root or Path("~/Papers/Paperflow/Quarantine/ImportedSources").expanduser()
    target_dir = quarantine_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    rows = []
    for row in audit.get("items", []):
        source = Path(row["source_path"]).expanduser()
        target = target_dir / source.name
        can_move = (
            row.get("audit_passed")
            and row.get("vault_pdf_exists")
            and source.exists()
        )
        event = {
            "source_path": str(source),
            "quarantine_path": str(target),
            "can_move": can_move,
            "moved": False,
            "reason": None if can_move else "audit/source/vault precondition failed",
        }
        if apply and can_move:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            event["moved"] = True
        rows.append(event)
    return {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "mode": "apply" if apply else "report-only",
        "items": rows,
    }


def write_source_cleanup_report(report: dict[str, Any], path: Path) -> None:
    ensure_parent_dir(path)
    lines = ["# local source cleanup report", "", f"- Mode: {report.get('mode')}", ""]
    for row in report.get("items", []):
        lines.append(f"- moved={row['moved']} can_move={row['can_move']}: `{row['source_path']}` -> `{row['quarantine_path']}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
