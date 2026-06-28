from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pypdf import PdfReader

from paperflow.metadata import (
    DOI_RE,
    arxiv_id_from_attachment_filename,
    arxiv_id_from_doi,
    arxiv_id_from_extra,
    arxiv_id_from_url,
)
from paperflow.taxonomy_v2 import normalize_doi
from paperflow.utils import ensure_parent_dir
from paperflow.vault import (
    DEFAULT_VAULT_LIBRARY,
    dedupe_target_path,
    target_path_for_item,
    zotero_linked_attachment_path,
)
from paperflow.zotero_local import extract_year
from paperflow.zotero_web import ZoteroWebClient


class StorageMode(StrEnum):
    LINKED_LOCAL = "linked-local"


INGEST_CONFIRMATION = "INGEST LOCAL PDFS"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_pdf_metadata_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"untitled", "none"}:
        return None
    return text


def _first_page_text(path: Path, limit: int = 4000) -> str:
    try:
        reader = PdfReader(str(path))
        if not reader.pages:
            return ""
        text = reader.pages[0].extract_text() or ""
        return text[:limit]
    except Exception:
        return ""


def extract_pdf_metadata(path: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    try:
        reader = PdfReader(str(path))
        raw = reader.metadata or {}
        metadata["title"] = _clean_pdf_metadata_value(raw.get("/Title"))
        metadata["author"] = _clean_pdf_metadata_value(raw.get("/Author"))
        metadata["creation_date"] = _clean_pdf_metadata_value(raw.get("/CreationDate"))
    except Exception:
        metadata["title"] = None
        metadata["author"] = None
        metadata["creation_date"] = None

    first_page = _first_page_text(path)
    combined = " ".join(
        value
        for value in [
            path.name,
            metadata.get("title") or "",
            metadata.get("author") or "",
            first_page,
        ]
        if value
    )
    doi_match = DOI_RE.search(combined)
    doi = normalize_doi(doi_match.group(0)) if doi_match else None
    arxiv_id = (
        arxiv_id_from_attachment_filename(path.name)
        or arxiv_id_from_doi(doi)
        or arxiv_id_from_url(combined)
        or arxiv_id_from_extra(combined)
    )
    title = metadata.get("title") or path.stem.replace("_", " ").replace("-", " ").strip()
    year = extract_year(metadata.get("creation_date")) or extract_year(combined)
    identifier = arxiv_id or doi or sha256_file(path)[:12]
    metadata.update(
        {
            "title": title,
            "year": year,
            "doi_normalized": doi,
            "arxiv_id": arxiv_id,
            "identifier": identifier,
        }
    )
    return metadata


def _pseudo_item_for_pdf(path: Path, metadata: dict[str, Any]) -> SimpleNamespace:
    identifier = metadata.get("identifier") or path.stem or "unknown"
    return SimpleNamespace(
        item_key=identifier,
        key=identifier,
        year=metadata.get("year"),
        title=metadata.get("title") or path.stem,
        arxiv_id=metadata.get("arxiv_id"),
        doi_normalized=metadata.get("doi_normalized"),
        doi=metadata.get("doi_normalized"),
    )


def build_ingest_plan(
    pdf_paths: list[Path],
    vault_library: Path = DEFAULT_VAULT_LIBRARY,
) -> dict[str, Any]:
    seen: set[Path] = set()
    items: list[dict[str, Any]] = []
    for raw_path in pdf_paths:
        source = raw_path.expanduser()
        metadata = extract_pdf_metadata(source) if source.exists() else {}
        target = dedupe_target_path(
            target_path_for_item(_pseudo_item_for_pdf(source, metadata), vault_library),
            seen,
            source.stem,
        )
        items.append(
            {
                "source_path": str(source),
                "source_exists": source.exists(),
                "source_sha256": sha256_file(source) if source.exists() else None,
                "target_path": str(target),
                "title": metadata.get("title") or source.stem,
                "year": metadata.get("year"),
                "doi_normalized": metadata.get("doi_normalized"),
                "arxiv_id": metadata.get("arxiv_id"),
                "identifier": metadata.get("identifier") or source.stem,
                "zotero_action": "create-or-update-parent-and-linked-attachment",
                "storage_mode": StorageMode.LINKED_LOCAL.value,
            }
        )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vault_library": str(vault_library.expanduser()),
        "items": items,
    }


def write_ingest_report(plan: dict[str, Any], path: Path, applied: bool = False) -> None:
    ensure_parent_dir(path)
    lines = [
        "# ingest report",
        "",
        f"- Mode: {'apply' if applied else 'dry-run'}",
        f"- Storage mode: {StorageMode.LINKED_LOCAL.value}",
        f"- PDFs: {len(plan['items'])}",
        f"- Vault library: {plan['vault_library']}",
        "",
        "No PDF bytes are uploaded to Zotero Storage. Zotero receives metadata and linked attachment records only.",
        "",
        "## Files",
        "",
    ]
    for item in plan["items"]:
        exists = "yes" if item["source_exists"] else "no"
        lines.append(
            f"- `{item['source_path']}` -> `{item['target_path']}` "
            f"(source exists: {exists})"
        )
    if not plan["items"]:
        lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_ingest_request(
    pdf_paths: list[Path],
    storage_mode: StorageMode,
    apply: bool,
    dry_run: bool,
    user_id: str | None,
    api_key: str | None,
) -> None:
    if storage_mode != StorageMode.LINKED_LOCAL:
        raise ValueError("Only --storage-mode linked-local is supported.")
    if apply and dry_run:
        raise ValueError("Use either --dry-run or --apply, not both.")
    if not apply and not dry_run:
        raise ValueError("Default is dry-run; pass --dry-run explicitly or --apply.")
    if not pdf_paths:
        raise ValueError("At least one PDF path is required.")
    invalid = [str(path) for path in pdf_paths if path.suffix.lower() != ".pdf"]
    if invalid:
        raise ValueError(f"Only .pdf files are accepted: {invalid}")
    if apply:
        if not user_id or not api_key:
            raise ValueError("ZOTERO_USER_ID and ZOTERO_API_KEY must be set for --apply.")
        if not user_id.isdigit():
            raise ValueError("ZOTERO_USER_ID must be your numeric Zotero user ID.")


def copy_pdf_to_vault(source: Path, target: Path, expected_sha256: str | None) -> str:
    if not source.exists():
        raise FileNotFoundError(f"PDF not found: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        existing_sha = sha256_file(target)
        if expected_sha256 and existing_sha == expected_sha256:
            return existing_sha
        raise FileExistsError(f"Target exists with different content: {target}")
    shutil.copy2(source, target)
    actual = sha256_file(target)
    if expected_sha256 and actual != expected_sha256:
        target.unlink(missing_ok=True)
        raise ValueError(f"Checksum mismatch after copy: {target}")
    return actual


def _item_arxiv_id(raw_item: dict[str, Any]) -> str | None:
    data = raw_item.get("data", {})
    doi = normalize_doi(data.get("DOI") or data.get("doi"))
    return (
        arxiv_id_from_doi(doi)
        or arxiv_id_from_url(data.get("url"))
        or arxiv_id_from_extra(data.get("extra"))
    )


def _find_existing_parent(client: ZoteroWebClient, plan_item: dict[str, Any]) -> str | None:
    doi = plan_item.get("doi_normalized")
    arxiv_id = plan_item.get("arxiv_id")
    if not doi and not arxiv_id:
        return None
    for raw_item in client.iter_top_items():
        data = raw_item.get("data", {})
        if doi and normalize_doi(data.get("DOI") or data.get("doi")) == doi:
            return str(raw_item.get("key") or data.get("key"))
        if arxiv_id and _item_arxiv_id(raw_item) == arxiv_id:
            return str(raw_item.get("key") or data.get("key"))
    return None


def _created_key(response_json: dict[str, Any], index: int = 0) -> str:
    successful = response_json.get("successful", {})
    row = successful.get(str(index)) or successful.get(index)
    if isinstance(row, dict):
        data = row.get("data", {})
        key = row.get("key") or data.get("key")
        if key:
            return str(key)
    raise ValueError(f"Could not parse Zotero create response: {response_json}")


def _parent_body(plan_item: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "itemType": "journalArticle",
        "title": plan_item["title"],
        "tags": [{"tag": "source/arxiv"}] if plan_item.get("arxiv_id") else [],
    }
    if plan_item.get("doi_normalized"):
        body["DOI"] = plan_item["doi_normalized"]
    if plan_item.get("year"):
        body["date"] = str(plan_item["year"])
    if plan_item.get("arxiv_id"):
        body["url"] = f"https://arxiv.org/abs/{plan_item['arxiv_id']}"
    return body


def linked_attachment_body(
    parent_key: str,
    pdf_path: Path,
    title: str | None = None,
    vault_library: Path = DEFAULT_VAULT_LIBRARY,
) -> dict[str, Any]:
    return {
        "itemType": "attachment",
        "parentItem": parent_key,
        "linkMode": "linked_file",
        "title": title or pdf_path.name,
        "path": zotero_linked_attachment_path(pdf_path, vault_library=vault_library),
        "filename": pdf_path.name,
        "contentType": "application/pdf",
    }


def apply_ingest_plan(
    plan: dict[str, Any],
    user_id: str,
    api_key: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    vault_library = Path(plan["vault_library"]).expanduser()
    with ZoteroWebClient(user_id=user_id, api_key=api_key) as client:
        for item in plan["items"]:
            source = Path(item["source_path"])
            target = Path(item["target_path"])
            checksum = copy_pdf_to_vault(source, target, item.get("source_sha256"))
            events.append(
                {
                    "event": "pdf-copied-to-vault",
                    "sourcePath": str(source),
                    "targetPath": str(target),
                    "sha256": checksum,
                }
            )

            parent_key = _find_existing_parent(client, item)
            if parent_key:
                events.append({"event": "parent-item-found", "itemKey": parent_key})
            else:
                response = client.post_items([_parent_body(item)])
                parent_key = _created_key(response.json())
                events.append(
                    {
                        "event": "parent-item-created",
                        "itemKey": parent_key,
                        "statusCode": response.status_code,
                    }
                )

            response = client.post_items(
                [
                    linked_attachment_body(
                        parent_key,
                        target,
                        title=item["title"],
                        vault_library=vault_library,
                    )
                ]
            )
            attachment_key = _created_key(response.json())
            events.append(
                {
                    "event": "linked-attachment-created",
                    "parentItemKey": parent_key,
                    "attachmentKey": attachment_key,
                    "path": str(target),
                    "statusCode": response.status_code,
                }
            )
    return events
