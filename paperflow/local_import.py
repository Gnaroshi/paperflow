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
    COLLECTION_TREE_V3,
    REVIEW_QUEUE_COLLECTION,
    TAG_VOCABULARY_V3,
    area_slug_from_collection,
    clamp_tags_v3,
    normalize_title_v3,
    unique_preserve_order,
)
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
    local_path = str(Path(scan_row.get("path")).expanduser())
    local_sha = scan_row.get("sha256")
    best_possible: tuple[float, dict[str, Any], str] | None = None
    best_likely: tuple[float, dict[str, Any], str] | None = None

    for item in zotero_items:
        if doi and doi == item.get("doi_normalized"):
            return match_result(scan_row, item, "exact_existing", "same DOI", 1.0)
        if arxiv_id and arxiv_id == item.get("arxiv_id"):
            return match_result(scan_row, item, "exact_existing", "same arXiv ID", 1.0)
        if local_base and local_base == item.get("arxiv_base_id"):
            if newer_arxiv_version(arxiv_id, item.get("arxiv_id")):
                return match_result(scan_row, item, "update_candidate", "newer arXiv version", 0.97)
            return match_result(scan_row, item, "exact_existing", "same arXiv base ID", 0.98)
        if local_sha and local_sha in set(item.get("attachment_sha256", [])):
            return match_result(scan_row, item, "exact_existing", "same PDF SHA256", 1.0)
        if local_path in set(item.get("attachment_paths", [])):
            return match_result(scan_row, item, "exact_existing", "same attachment local path", 1.0)
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
            best_likely = max_match(best_likely, (0.94, item, "same normalized title"))
        similarity = best_title_similarity(scan_row, item)
        if similarity >= 96 and year_close(local_year, item.get("year")):
            best_likely = max_match(best_likely, (similarity / 100, item, "fuzzy title >= 0.96 and year within +/-1"))
        elif similarity >= 90:
            best_possible = max_match(best_possible, (similarity / 100, item, "fuzzy title >= 0.90"))

    if best_likely:
        confidence, item, reason = best_likely
        return match_result(scan_row, item, "likely_existing", reason, confidence)
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
    return {
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


def match_local_to_zotero(scan: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    matches = [match_scan_row(row, index.get("items", [])) for row in scan.get("files", [])]
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


def classify_scan_row(row: dict[str, Any], forced_review: str | None = None) -> dict[str, Any]:
    detected = row.get("detected", {})
    if forced_review:
        cleanup_collection = (
            "AI Library/40 Cleanup/Update Candidates"
            if forced_review == "update_candidate"
            else "AI Library/40 Cleanup/Possible Existing in Zotero"
        )
        return {
            "target_collections": [REVIEW_QUEUE_COLLECTION, cleanup_collection],
            "normalized_tags": clamp_tags_v3(
                [
                    "status/to-read",
                    "cleanup/update-candidate" if forced_review == "update_candidate" else "cleanup/possible-existing",
                    "source/arxiv" if detected.get("arxiv_id") else "source/unknown",
                ]
            ),
            "confidence": 0.2,
            "rationale": f"sent to review because match_status={forced_review}",
        }
    text = classify_text(row)
    collections: list[str] = []
    tags = ["status/to-read"]
    reasons: list[str] = []

    def add(collection: str, *new_tags: str, reason: str) -> None:
        collections.append(collection)
        tags.extend(new_tags)
        reasons.append(reason)

    if strict_rag_signal(text):
        add("AI Library/20 Areas/LLM/RAG & Retrieval", "area/rag", "method/retrieval", "method/rag", reason="explicit retrieval/RAG signal")
    if any(term in text for term in ("world model", "looped world", "recurrent depth", "adaptive computation")):
        add("AI Library/20 Areas/Embodied AI/World Models", "area/world-models", "method/world-model", "method/adaptive-computation", reason="world model/adaptive computation signal")
    if any(term in text for term in ("robot", "manipulation", "imitation learning", "policy learning", "vla", "vision language action")):
        add("AI Library/20 Areas/Embodied AI/Robot Manipulation", "area/robot-manipulation", "task/robot-manipulation", "method/control", reason="robot manipulation/VLA signal")
    if any(term in text for term in ("clip", "vision language", "vision-language", "vlm")):
        add("AI Library/20 Areas/Vision-Language/CLIP & Contrastive VLM", "area/vlm-contrastive", "task/multimodal-understanding", reason="vision-language signal")
    if any(term in text for term in ("prompt learning", "coop", "cocoop")):
        add("AI Library/20 Areas/Vision-Language/Prompt Learning", "area/vlm-prompt-learning", "method/prompting", reason="VLM prompt learning signal")
    if any(term in text for term in ("document understanding", "chart", "ocr", "document ai")):
        add("AI Library/20 Areas/Vision-Language/Document & Chart Understanding", "area/document-understanding", "task/multimodal-understanding", reason="document/chart understanding signal")
    if any(term in text for term in ("battery", "state of health", "soh", "rul", "cycle life", "degradation")):
        add("AI Library/20 Areas/Battery ML/SOH & RUL Prognostics", "area/battery-ml", "task/battery-prognostics", "task/rul-prediction", reason="battery prognostics signal")
    if any(term in text for term in ("anomaly", "defect", "mvtec", "industrial inspection")):
        add("AI Library/20 Areas/Computer Vision/Anomaly & Defect Detection", "area/anomaly-detection", "task/anomaly-detection", reason="anomaly/defect detection signal")
    if any(term in text for term in ("x-ray", "radiology", "chest", "biomedical", "medical image")):
        add("AI Library/20 Areas/Medical AI/Radiology & X-ray", "area/medical-ai", "task/medical-diagnosis", reason="medical imaging signal")
    if any(term in text for term in ("yolo", "faster r-cnn", "detr", "object detection", "bounding box")):
        add("AI Library/20 Areas/Computer Vision/Object Detection", "area/object-detection", "task/object-detection", reason="object detection signal")
    if any(term in text for term in ("segmentation", "u-net", "mask r-cnn", "sam ")):
        add("AI Library/20 Areas/Computer Vision/Segmentation", "area/segmentation", "task/segmentation", reason="segmentation signal")
    if any(term in text for term in ("graph neural", "gnn", "graph convolution")):
        add("AI Library/20 Areas/Graph Learning/GNNs", "area/graph-learning", "method/gnn", reason="GNN signal")
    if any(term in text for term in ("knowledge graph", "kg ")):
        add("AI Library/20 Areas/Graph Learning/Knowledge Graphs", "area/graph-learning", reason="knowledge graph signal")
    if any(term in text for term in ("time series", "forecast", "temporal")):
        add("AI Library/20 Areas/Time-Series/Forecasting", "area/time-series", reason="time-series signal")
    if any(term in text for term in ("neural ode", "dynamical system", "controlled differential")):
        add("AI Library/20 Areas/Time-Series/Dynamical Systems", "area/dynamical-systems", reason="dynamical systems signal")
    if any(term in text for term in ("kv cache", "cache compression", "efficient inference", "quantization", "distillation", "compression")):
        add("AI Library/20 Areas/Efficient ML/Inference & KV Cache", "area/efficient-ml", "method/efficient-compute", reason="efficient inference/compression signal")
    if any(term in text for term in ("jailbreak", "alignment", "hallucination", "safety")):
        add("AI Library/20 Areas/LLM/Alignment, Safety & Hallucination", "area/alignment-safety", "method/alignment", reason="alignment/safety signal")
    if any(term in text for term in ("survey", "review", "tutorial")):
        add("AI Library/30 Resources/Surveys & Tutorials", "type/survey", reason="survey/tutorial signal")
    if any(term in text for term in ("attention is all you need", "resnet", "alexnet", "batch normalization", "vit ", "u-net")):
        add("AI Library/30 Resources/Foundational Papers", "type/foundational", reason="foundational title signal")

    if "transformer" in text:
        tags.append("method/transformer")
    if "cnn" in text or "convolution" in text:
        tags.append("method/cnn")
    if "contrastive" in text:
        tags.append("method/contrastive-learning")
    if "self-supervised" in text:
        tags.append("method/self-supervised-learning")
    if "diffusion" in text:
        tags.append("method/diffusion")
    if detected.get("arxiv_id"):
        tags.append("source/arxiv")
    else:
        tags.append("source/unknown")
    tags.append("type/method")

    collections = unique_preserve_order(collections)[:3]
    confidence = min(0.95, 0.52 + 0.14 * len(collections))
    if not collections:
        collections = [REVIEW_QUEUE_COLLECTION]
        confidence = 0.25
        reasons.append("no fine-grained taxonomy rule matched")
    return {
        "target_collections": collections,
        "normalized_tags": clamp_tags_v3(tags),
        "confidence": round(confidence, 2),
        "rationale": "; ".join(unique_preserve_order(reasons)),
    }


def strict_rag_signal(text: str) -> bool:
    patterns = (
        "retrieval augmented generation",
        "retrieval-augmented generation",
        "rag",
        "retriever",
        "document retrieval",
        "passage retrieval",
        "dense retrieval",
        "indexing",
        "knowledge-base retrieval",
        "citation-grounded",
        "query-document",
    )
    return any(pattern in text for pattern in patterns)


def classify_new_local_papers(
    scan: dict[str, Any],
    matches: dict[str, Any],
    include_possible_existing: bool = False,
    include_update_candidates: bool = False,
) -> dict[str, Any]:
    match_by_path = {row["local_path"]: row for row in matches.get("matches", [])}
    items: list[dict[str, Any]] = []
    for row in scan.get("files", []):
        match = match_by_path.get(row.get("path"))
        status = match.get("match_status") if match else "new"
        if status in {"exact_existing", "likely_existing", "error"}:
            continue
        if status == "possible_existing" and not include_possible_existing:
            items.append(build_classification_item(row, match, classify_scan_row(row, "possible_existing"), "review"))
            continue
        if status == "update_candidate" and not include_update_candidates:
            items.append(build_classification_item(row, match, classify_scan_row(row, "update_candidate"), "review"))
            continue
        if status == "new" or include_possible_existing or include_update_candidates:
            items.append(build_classification_item(row, match, classify_scan_row(row), "import"))
    return {
        "schema_version": "1.0",
        "taxonomy_version": "3.0",
        "generated_at": utc_now(),
        "collection_tree": COLLECTION_TREE_V3,
        "tag_vocabulary": TAG_VOCABULARY_V3,
        "items": items,
    }


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
        "gemini_used": False,
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
