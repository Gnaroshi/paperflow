from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
from pypdf import PdfReader

from paperflow.metadata import (
    DOI_RE,
    arxiv_id_from_attachment_filename,
    arxiv_id_from_doi,
    arxiv_id_from_extra,
    arxiv_id_from_url,
)
from paperflow.migration_apply import collection_maps, creation_plan
from paperflow.taxonomy_v2 import normalize_doi
from paperflow.utils import ensure_parent_dir
from paperflow.vault import (
    DEFAULT_VAULT_LIBRARY,
    dedupe_target_path,
    safe_pdf_filename,
    zotero_linked_attachment_path,
)
from paperflow.zotero_local import extract_year
from paperflow.zotero_web import ZoteroWebClient


class StorageMode(StrEnum):
    LINKED_LOCAL = "linked-local"


INGEST_CONFIRMATION = "INGEST LOCAL PDFS"

INGEST_STAGES = (
    "validate_files",
    "inspect_pdf",
    "extract_filename_identifiers",
    "extract_first_page_text",
    "extract_arxiv_id",
    "fetch_arxiv_metadata",
    "detect_doi",
    "fetch_doi_metadata",
    "classify",
    "plan_filename",
    "plan_zotero_actions",
    "write_dry_run_report",
    "done",
)

ProgressWriter = Callable[[dict[str, Any]], None]


class ProgressEmitter:
    def __init__(
        self,
        enabled: bool = False,
        writer: ProgressWriter | None = None,
        heartbeat_seconds: float = 3.0,
    ) -> None:
        self.enabled = enabled
        self.writer = writer or self._default_writer
        self.heartbeat_seconds = heartbeat_seconds
        self.started_at = time.monotonic()

    def emit(
        self,
        event: str,
        stage: str,
        message: str,
        file_path: str | None = None,
        file_index: int | None = None,
        total_files: int | None = None,
        **extra: Any,
    ) -> None:
        if not self.enabled:
            return
        payload = {
            "event": event,
            "stage": stage,
            "message": message,
            "elapsed_ms": int((time.monotonic() - self.started_at) * 1000),
            "file_path": file_path,
            "file_index": file_index,
            "total_files": total_files,
        }
        payload.update(extra)
        self.writer(payload)

    @contextmanager
    def stage(
        self,
        stage: str,
        message: str,
        file_path: str | None = None,
        file_index: int | None = None,
        total_files: int | None = None,
        heartbeat_message: str | None = None,
    ) -> Iterator[None]:
        self.emit(
            "stage_started",
            stage,
            message,
            file_path=file_path,
            file_index=file_index,
            total_files=total_files,
        )
        stop = threading.Event()

        def heartbeat() -> None:
            while not stop.wait(self.heartbeat_seconds):
                self.emit(
                    "heartbeat",
                    stage,
                    heartbeat_message or f"Still running {stage}...",
                    file_path=file_path,
                    file_index=file_index,
                    total_files=total_files,
                )

        thread: threading.Thread | None = None
        if self.enabled:
            thread = threading.Thread(target=heartbeat, daemon=True)
            thread.start()
        try:
            yield
            self.emit(
                "stage_finished",
                stage,
                f"Finished {stage}",
                file_path=file_path,
                file_index=file_index,
                total_files=total_files,
            )
        finally:
            stop.set()
            if thread is not None:
                thread.join(timeout=0.1)

    @staticmethod
    def _default_writer(payload: dict[str, Any]) -> None:
        print(json.dumps(payload, ensure_ascii=False), flush=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_first_mb(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        digest.update(input_file.read(1024 * 1024))
    return digest.hexdigest()


def _safe_cache_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "unknown"


def cache_get(cache_dir: Path, namespace: str, key: str) -> dict[str, Any] | None:
    path = cache_dir / namespace / f"{_safe_cache_name(key)}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def cache_put(cache_dir: Path, namespace: str, key: str, value: dict[str, Any]) -> None:
    path = cache_dir / namespace / f"{_safe_cache_name(key)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


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


def _pdf_page_count(path: Path) -> int | None:
    try:
        reader = PdfReader(str(path))
        return len(reader.pages)
    except Exception:
        return None


def _first_page_title(text: str) -> str | None:
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
        if re.sub(r"\s+", " ", line).strip()
    ]
    for line in lines[:12]:
        lowered = line.lower()
        if lowered.startswith(
            (
                "arxiv:",
                "abstract",
                "keywords",
                "submitted",
                "under review",
                "published by",
                "leading contributors",
                "core contributors",
            )
        ):
            continue
        if "research asia" in lowered or "contributors" in lowered:
            continue
        if "@" in line or len(line) > 140:
            continue
        if len(line.split()) <= 12 and any(char.isalpha() for char in line):
            return _prettify_pdf_title(line.rstrip("."))
    return None


def _prettify_pdf_title(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    compact = re.sub(r"[^A-Za-z0-9]+", "", text)
    if compact.upper() == "LOOPEDWORLDMODELS":
        return "Looped World Models"
    if text.isupper():
        return text.title()
    return text


def _abstract_from_first_page(text: str) -> str | None:
    match = re.search(
        r"(?is)\babstract\b\s*[:.\-]?\s+(?P<body>.+?)(?=\n\s*(?:1\s+introduction\b|introduction\b|keywords?\b)|$)",
        text,
    )
    if not match:
        return None
    abstract = re.sub(r"\s+", " ", match.group("body")).strip()
    return abstract if len(abstract) >= 80 else None


def _collapse_home(path: Path) -> str:
    expanded = str(path.expanduser())
    home = str(Path.home())
    if expanded == home:
        return "~"
    if expanded.startswith(f"{home}/"):
        return f"~/{expanded[len(home) + 1:]}"
    return expanded


def _authors_from_metadata(value: object) -> list[str]:
    if not value:
        return []
    return [
        author.strip()
        for author in re.split(r"\s*(?:;|,|\band\b)\s*", str(value))
        if author.strip()
    ][:20]


def ingest_actions(executed: bool = False) -> list[dict[str, Any]]:
    return [
        {"name": "copy_to_vault", "executed": executed},
        {"name": "create_or_update_zotero_item", "executed": executed},
        {"name": "create_linked_attachment", "executed": executed},
        {"name": "add_to_collections", "executed": executed},
        {"name": "add_tags", "executed": executed},
    ]


def _set_action(
    item: dict[str, Any],
    name: str,
    executed: bool,
    **extra: Any,
) -> None:
    for action in item.setdefault("actions", ingest_actions()):
        if action.get("name") == name:
            action["executed"] = executed
            action.update(extra)
            return
    item["actions"].append({"name": name, "executed": executed, **extra})


def arxiv_id_from_filename_preserve_version(value: str | None) -> str | None:
    if not value:
        return None
    filename = Path(value).name
    if DOI_RE.search(filename):
        return None
    match = re.search(
        r"(?<![\d.])(?P<id>(?:\d{2})(?:0[1-9]|1[0-2])\.\d{4,5}v\d+)(?:\.pdf)?(?:$|[^\d.])",
        filename,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group("id").lower()
    match = re.search(
        r"(?<![\d.])(?P<id>(?:\d{2})(?:0[1-9]|1[0-2])\.\d{4,5})(?:\.pdf)?(?:$|[^\d.])",
        filename,
        flags=re.IGNORECASE,
    )
    return match.group("id").lower() if match else None


def _strip_xml(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", text).strip() or None


def fetch_arxiv_metadata(
    arxiv_id: str,
    cache_dir: Path = Path("data/cache"),
    timeout_seconds: float = 10,
    network_enabled: bool = True,
) -> dict[str, Any]:
    cache_key = arxiv_id.lower()
    cached = cache_get(cache_dir, "arxiv", cache_key)
    if cached is not None:
        return {**cached, "cache_hit": True}
    if not network_enabled:
        return {"metadata_source": None, "cache_hit": False, "error": "network_disabled"}
    try:
        normalized = re.sub(r"v\d+$", "", arxiv_id, flags=re.IGNORECASE)
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get("https://export.arxiv.org/api/query", params={"id_list": normalized})
            response.raise_for_status()
        title = _strip_xml((re.search(r"<title>\s*(.*?)\s*</title>", response.text, flags=re.S) or [None, None])[1])
        summary = _strip_xml((re.search(r"<summary>\s*(.*?)\s*</summary>", response.text, flags=re.S) or [None, None])[1])
        published = _strip_xml((re.search(r"<published>\s*(.*?)\s*</published>", response.text, flags=re.S) or [None, None])[1])
        payload = {
            "metadata_source": "arxiv",
            "title": title if title and title.lower() != "arxiv query: search results" else None,
            "abstract": summary,
            "year": extract_year(published),
            "url": f"https://arxiv.org/abs/{arxiv_id}",
        }
        cache_put(cache_dir, "arxiv", cache_key, payload)
        return {**payload, "cache_hit": False}
    except Exception as exc:
        return {"metadata_source": None, "cache_hit": False, "error": str(exc)}


def fetch_doi_metadata(
    doi: str,
    cache_dir: Path = Path("data/cache"),
    timeout_seconds: float = 10,
    network_enabled: bool = True,
) -> dict[str, Any]:
    cache_key = doi.lower()
    cached = cache_get(cache_dir, "crossref", cache_key)
    if cached is not None:
        return {**cached, "cache_hit": True}
    if not network_enabled:
        return {"metadata_source": None, "cache_hit": False, "error": "network_disabled"}
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(f"https://api.crossref.org/works/{doi}")
            response.raise_for_status()
        message = response.json().get("message") or {}
        year = ((message.get("published-print") or message.get("published-online") or {}).get("date-parts") or [[None]])[0][0]
        payload = {
            "metadata_source": "doi",
            "title": (message.get("title") or [None])[0],
            "abstract": _strip_xml(message.get("abstract")),
            "year": year,
            "url": message.get("URL"),
            "publication_title": (message.get("container-title") or [None])[0],
        }
        cache_put(cache_dir, "crossref", cache_key, payload)
        return {**payload, "cache_hit": False}
    except Exception as exc:
        return {"metadata_source": None, "cache_hit": False, "error": str(exc)}


def extract_pdf_metadata(
    path: Path,
    network_enabled: bool = True,
    network_timeout_seconds: float = 10,
    cache_dir: Path = Path("data/cache"),
    progress: ProgressEmitter | None = None,
    file_index: int | None = None,
    total_files: int | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    progress = progress or ProgressEmitter(enabled=False)
    file_path = str(path)
    try:
        with progress.stage(
            "inspect_pdf",
            f"Inspecting PDF {path.name}",
            file_path=file_path,
            file_index=file_index,
            total_files=total_files,
            heartbeat_message="Still inspecting PDF...",
        ):
            reader = PdfReader(str(path))
            raw = reader.metadata or {}
            metadata["title"] = _clean_pdf_metadata_value(raw.get("/Title"))
            metadata["author"] = _clean_pdf_metadata_value(raw.get("/Author"))
            metadata["creation_date"] = _clean_pdf_metadata_value(raw.get("/CreationDate"))
            metadata["page_count"] = len(reader.pages)
    except Exception:
        metadata["title"] = None
        metadata["author"] = None
        metadata["creation_date"] = None
        metadata["page_count"] = None

    with progress.stage(
        "extract_filename_identifiers",
        f"Extracting identifiers from filename {path.name}",
        file_path=file_path,
        file_index=file_index,
        total_files=total_files,
    ):
        filename_arxiv_id = arxiv_id_from_filename_preserve_version(path.name)

    with progress.stage(
        "extract_first_page_text",
        f"Extracting first page text from {path.name}",
        file_path=file_path,
        file_index=file_index,
        total_files=total_files,
        heartbeat_message="Still extracting first page text...",
    ):
        first_page = _first_page_text(path)
        first_page_title = _first_page_title(first_page)
        first_page_abstract = _abstract_from_first_page(first_page)

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

    with progress.stage(
        "extract_arxiv_id",
        f"Extracting arXiv ID for {path.name}",
        file_path=file_path,
        file_index=file_index,
        total_files=total_files,
    ):
        arxiv_id = (
            filename_arxiv_id
            or arxiv_id_from_attachment_filename(path.name)
            or arxiv_id_from_doi(doi)
            or arxiv_id_from_url(combined)
            or arxiv_id_from_extra(combined)
        )

    arxiv_metadata: dict[str, Any] = {}
    if arxiv_id:
        with progress.stage(
            "fetch_arxiv_metadata",
            f"Fetching arXiv metadata for {arxiv_id}",
            file_path=file_path,
            file_index=file_index,
            total_files=total_files,
            heartbeat_message="Still fetching arXiv metadata...",
        ):
            try:
                arxiv_metadata = fetch_arxiv_metadata(
                    arxiv_id,
                    cache_dir=cache_dir,
                    timeout_seconds=network_timeout_seconds,
                    network_enabled=network_enabled,
                )
            except Exception as exc:
                arxiv_metadata = {"metadata_source": None, "cache_hit": False, "error": str(exc)}
    else:
        progress.emit(
            "stage_skipped",
            "fetch_arxiv_metadata",
            "No arXiv ID found; skipping arXiv metadata.",
            file_path=file_path,
            file_index=file_index,
            total_files=total_files,
        )

    with progress.stage(
        "detect_doi",
        f"Detecting DOI for {path.name}",
        file_path=file_path,
        file_index=file_index,
        total_files=total_files,
    ):
        doi = doi

    doi_metadata: dict[str, Any] = {}
    if doi:
        with progress.stage(
            "fetch_doi_metadata",
            f"Fetching DOI metadata for {doi}",
            file_path=file_path,
            file_index=file_index,
            total_files=total_files,
            heartbeat_message="Still fetching DOI metadata...",
        ):
            try:
                doi_metadata = fetch_doi_metadata(
                    doi,
                    cache_dir=cache_dir,
                    timeout_seconds=network_timeout_seconds,
                    network_enabled=network_enabled,
                )
            except Exception as exc:
                doi_metadata = {"metadata_source": None, "cache_hit": False, "error": str(exc)}
    else:
        progress.emit(
            "stage_skipped",
            "fetch_doi_metadata",
            "No DOI found; skipping DOI metadata.",
            file_path=file_path,
            file_index=file_index,
            total_files=total_files,
        )

    title = (
        arxiv_metadata.get("title")
        or doi_metadata.get("title")
        or first_page_title
        or metadata.get("title")
        or path.stem.replace("_", " ").replace("-", " ").strip()
    )
    year = (
        arxiv_metadata.get("year")
        or doi_metadata.get("year")
        or extract_year(metadata.get("creation_date"))
        or extract_year(combined)
    )
    abstract = arxiv_metadata.get("abstract") or doi_metadata.get("abstract") or first_page_abstract
    if arxiv_metadata.get("abstract"):
        abstract_source = "arxiv"
    elif doi_metadata.get("abstract"):
        abstract_source = "doi"
    elif first_page_abstract:
        abstract_source = "pdf_first_page"
    else:
        abstract_source = None
    metadata_sources = ["filename"]
    if first_page_title or first_page_abstract:
        metadata_sources.append("pdf_first_page")
    if arxiv_metadata.get("metadata_source"):
        metadata_sources.append("arxiv")
    if doi_metadata.get("metadata_source"):
        metadata_sources.append("doi")
    metadata_source = "+".join(dict.fromkeys(metadata_sources))
    identifier = arxiv_id or doi or sha256_file(path)[:12]
    metadata.update(
        {
            "title": title,
            "year": year,
            "doi_normalized": doi,
            "arxiv_id": arxiv_id,
            "identifier": identifier,
            "display_identifier": f"arXiv {arxiv_id}" if arxiv_id else (doi or identifier),
            "abstract": abstract,
            "abstract_found": bool(abstract),
            "abstract_source": abstract_source,
            "metadata_source": metadata_source,
            "first_page_text": first_page,
            "first_page_sha256": sha256_first_mb(path),
            "arxiv_metadata_error": arxiv_metadata.get("error"),
            "doi_metadata_error": doi_metadata.get("error"),
        }
    )
    return metadata


def classify_ingest_metadata(metadata: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    text = " ".join(
        str(value or "")
        for value in [
            metadata.get("title"),
            metadata.get("abstract"),
            metadata.get("first_page_text"),
        ]
    ).lower()
    collections: list[str] = []
    tags = ["status/to-read"]
    reasons: list[str] = []
    if "looped world models" in text or "first looped architectures for world modelling" in text:
        collections.extend(
            [
                "AI Library/20 Areas/World Models & Simulation/Latent World Models",
                "AI Library/20 Areas/Recurrent & Adaptive Computation/Looped Transformers",
                "AI Library/20 Areas/Efficient ML Systems/Parameter Sharing",
            ]
        )
        tags.extend(
            [
                "area/world-models",
                "area/recurrent-adaptive-computation",
                "area/efficient-ml",
                "method/world-model",
                "method/looped-transformer",
                "method/recurrent-depth",
                "method/adaptive-computation",
                "method/parameter-sharing",
                "task/world-simulation",
            ]
        )
        reasons.append("matched looped world model deterministic rule")
    elif "world model" in text or "looped world" in text:
        collections.append("AI Library/20 Areas/World Models & Simulation/Latent World Models")
        tags.extend(["area/world-models", "method/world-model", "task/world-simulation"])
        reasons.append("matched world model terms")
    if any(term in text for term in ("parameter sharing", "parameter-shared", "adaptive computation", "efficient inference")):
        collections.append("AI Library/20 Areas/Efficient ML Systems/Parameter Sharing")
        tags.append("area/efficient-ml")
        if "adaptive computation" in text:
            tags.append("method/adaptive-computation")
        if "parameter" in text:
            tags.append("method/parameter-sharing")
        reasons.append("matched efficient/adaptive computation terms")
    if any(term in text for term in ("recurrent depth", "looped transformer", "universal transformer", "dynamic depth")):
        collections.append("AI Library/20 Areas/Recurrent & Adaptive Computation/Looped Transformers")
        tags.append("area/recurrent-adaptive-computation")
        reasons.append("matched recurrent/adaptive computation terms")
    if "transformer" in text:
        tags.append("method/transformer")
    if "looped transformer" in text or "looped world" in text:
        tags.append("method/looped-transformer")
    if "recurrent depth" in text:
        tags.append("method/recurrent-depth")
    if "adaptive computation" in text:
        tags.append("method/adaptive-computation")
    source_tag = "source/arxiv" if metadata.get("arxiv_id") else "source/unknown"
    if not collections:
        collections = ["AI Library/05 Review Queue/Ambiguous Classification"]
        tags.extend(["status/review-needed", "cleanup/low-confidence"])
        reasons.append("no strong ingest taxonomy signal")
    # Keep required source/type tags from being pushed out by optional method details.
    priority_tags = [
        "status/to-read",
        source_tag,
        "type/method",
        "area/world-models",
        "area/recurrent-adaptive-computation",
        "area/efficient-ml",
        "method/world-model",
        "method/transformer",
        "method/looped-transformer",
        "method/recurrent-depth",
        "method/adaptive-computation",
        "method/parameter-sharing",
        "task/world-simulation",
        "status/review-needed",
        "cleanup/low-confidence",
    ]
    available_tags = set(tags + [source_tag, "type/method"])
    seen: set[str] = set()
    cleaned = []
    for tag in priority_tags + tags:
        if tag not in available_tags:
            continue
        if tag not in seen:
            cleaned.append(tag)
            seen.add(tag)
    return list(dict.fromkeys(collections))[:3], cleaned[:15], reasons


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


def target_path_for_ingest_pdf(
    source: Path,
    metadata: dict[str, Any],
    vault_library: Path,
) -> Path:
    year = metadata.get("year")
    title = metadata.get("title") or source.stem
    identifier = metadata.get("display_identifier") or metadata.get("identifier") or source.stem
    filename = safe_pdf_filename(year, title, identifier)
    directory = vault_library.expanduser() / (str(year) if year else "unknown-year")
    return directory / filename


def build_ingest_plan(
    pdf_paths: list[Path],
    vault_library: Path = DEFAULT_VAULT_LIBRARY,
    progress: ProgressEmitter | None = None,
    network_enabled: bool = True,
    network_timeout_seconds: float = 10,
    cache_dir: Path = Path("data/cache"),
) -> dict[str, Any]:
    progress = progress or ProgressEmitter(enabled=False)
    seen: set[Path] = set()
    items: list[dict[str, Any]] = []
    total_files = len(pdf_paths)
    for index, raw_path in enumerate(pdf_paths, start=1):
        source = raw_path.expanduser()
        file_path = str(source)
        with progress.stage(
            "validate_files",
            f"Validating {total_files} PDF" if total_files == 1 else f"Validating {total_files} PDFs",
            file_path=file_path,
            file_index=index,
            total_files=total_files,
        ):
            exists = source.exists()
            source_size = source.stat().st_size if exists else None
        metadata = (
            extract_pdf_metadata(
                source,
                network_enabled=network_enabled,
                network_timeout_seconds=network_timeout_seconds,
                cache_dir=cache_dir,
                progress=progress,
                file_index=index,
                total_files=total_files,
            )
            if exists
            else {}
        )
        with progress.stage(
            "classify",
            f"Classifying {source.name}",
            file_path=file_path,
            file_index=index,
            total_files=total_files,
        ):
            target_collections, normalized_tags, classification_reasons = classify_ingest_metadata(metadata)
        with progress.stage(
            "plan_filename",
            f"Planning vault filename for {source.name}",
            file_path=file_path,
            file_index=index,
            total_files=total_files,
        ):
            target = dedupe_target_path(
                target_path_for_ingest_pdf(source, metadata, vault_library),
                seen,
                source.stem,
            )
        with progress.stage(
            "plan_zotero_actions",
            f"Planning Zotero linked attachment action for {source.name}",
            file_path=file_path,
            file_index=index,
            total_files=total_files,
        ):
            zotero_action = "create-or-update-parent-and-linked-attachment"
            planned_zotero_operation = "create"
        title = metadata.get("title") or source.stem
        abstract_found = bool(metadata.get("abstract_found"))
        planned_filename = target.name
        rationale = "; ".join(classification_reasons) if classification_reasons else "No strong ingest taxonomy signal."
        classification_confidence = (
            0.35
            if target_collections == ["AI Library/05 Review Queue/Ambiguous Classification"]
            else 0.82
        )
        items.append(
            {
                "source_path": str(source),
                "source_file": str(source),
                "source_exists": exists,
                "file_exists": exists,
                "source_size": source_size,
                "file_size_bytes": source_size,
                "source_sha256": sha256_file(source) if exists else None,
                "first_mb_sha256": metadata.get("first_page_sha256"),
                "target_path": str(target),
                "planned_filename": planned_filename,
                "planned_vault_path": _collapse_home(target),
                "title": title,
                "authors": _authors_from_metadata(metadata.get("author")),
                "year": metadata.get("year"),
                "doi_normalized": metadata.get("doi_normalized"),
                "doi": metadata.get("doi_normalized"),
                "arxiv_id": metadata.get("arxiv_id"),
                "identifier": metadata.get("identifier") or source.stem,
                "display_identifier": metadata.get("display_identifier") or metadata.get("identifier") or source.stem,
                "abstract_found": abstract_found,
                "abstract_present": abstract_found,
                "abstract_source": metadata.get("abstract_source"),
                "metadata_source": metadata.get("metadata_source"),
                "pdf_page_count": metadata.get("page_count"),
                "target_collections": target_collections,
                "planned_collections": target_collections,
                "normalized_tags": normalized_tags,
                "planned_tags": normalized_tags,
                "classification_reasons": classification_reasons,
                "classification": {
                    "confidence": classification_confidence,
                    "rationale": rationale,
                },
                "gemini_enabled": False,
                "network_enabled": network_enabled,
                "zotero_write_enabled": False,
                "zotero_action": zotero_action,
                "storage_mode": StorageMode.LINKED_LOCAL.value,
                "upload_to_zotero_storage": False,
                "zotero": {
                    "operation": planned_zotero_operation,
                    "item_key": None,
                    "open_uri": None,
                    "write_executed": False,
                },
                "actions": ingest_actions(executed=False),
            }
        )
    return {
        "schema_version": "1.0",
        "mode": "dry-run",
        "storage_mode": StorageMode.LINKED_LOCAL.value,
        "upload_to_zotero_storage": False,
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


def build_ingest_debug_trace(
    plan: dict[str, Any],
    gemini_enabled: bool = False,
    network_enabled: bool = True,
    zotero_write_enabled: bool = False,
) -> dict[str, Any]:
    return {
        "event": "debug_trace",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gemini_enabled": gemini_enabled,
        "network_enabled": network_enabled,
        "zotero_write_enabled": zotero_write_enabled,
        "files": [
            {
                "file_path": item["source_path"],
                "file_exists": item["source_exists"],
                "file_size": item.get("source_size"),
                "pdf_page_count": item.get("pdf_page_count"),
                "selected_metadata_source": item.get("metadata_source"),
                "title": item.get("title"),
                "arxiv_id": item.get("arxiv_id"),
                "doi_normalized": item.get("doi_normalized"),
                "abstract_found": item.get("abstract_found"),
                "planned_filename": Path(item["target_path"]).name,
                "planned_collections": item.get("target_collections", []),
                "planned_tags": item.get("normalized_tags", []),
                "classification_reasons": item.get("classification_reasons", []),
            }
            for item in plan["items"]
        ],
    }


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
    tags = plan_item.get("planned_tags") or plan_item.get("normalized_tags") or []
    body: dict[str, Any] = {
        "itemType": "journalArticle",
        "title": plan_item["title"],
        "tags": [{"tag": tag} for tag in tags],
    }
    if plan_item.get("doi_normalized"):
        body["DOI"] = plan_item["doi_normalized"]
    if plan_item.get("year"):
        body["date"] = str(plan_item["year"])
    if plan_item.get("arxiv_id"):
        body["url"] = f"https://arxiv.org/abs/{plan_item['arxiv_id']}"
    return body


def _ensure_ingest_collections(
    client: ZoteroWebClient,
    target_paths: list[str],
) -> dict[str, str]:
    collections = client.iter_collections()
    key_by_path, _, _ = collection_maps(collections)
    for collection in creation_plan(target_paths, collections):
        parent_path = collection["parentPath"]
        parent_key = key_by_path.get(parent_path) if parent_path else False
        response = client.post_collections(
            [{"name": collection["name"], "parentCollection": parent_key}]
        )
        response.raise_for_status()
        collections = client.iter_collections()
        key_by_path, _, _ = collection_maps(collections)
    return key_by_path


def _collection_keys_for_item(
    plan_item: dict[str, Any],
    key_by_path: dict[str, str],
) -> list[str]:
    return [
        key_by_path[path]
        for path in (plan_item.get("planned_collections") or plan_item.get("target_collections") or [])
        if path in key_by_path
    ]


def _zotero_open_uri(item_key: str) -> str:
    return f"zotero://select/library/items/{item_key}"


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
        collection_paths = list(
            dict.fromkeys(
                path
                for item in plan["items"]
                for path in (item.get("planned_collections") or item.get("target_collections") or [])
            )
        )
        key_by_path = _ensure_ingest_collections(client, collection_paths)
        for item in plan["items"]:
            item.setdefault(
                "zotero",
                {
                    "operation": "create",
                    "item_key": None,
                    "open_uri": None,
                    "write_executed": False,
                },
            )
            item.setdefault("actions", ingest_actions(executed=False))
            source = Path(item["source_path"])
            target = Path(item["target_path"])
            checksum = copy_pdf_to_vault(source, target, item.get("source_sha256"))
            _set_action(
                item,
                "copy_to_vault",
                True,
                source_file=str(source),
                linked_pdf_path=str(target),
                sha256=checksum,
            )
            events.append(
                {
                    "event": "pdf-copied-to-vault",
                    "sourcePath": str(source),
                    "targetPath": str(target),
                    "sha256": checksum,
                }
            )

            parent_key = _find_existing_parent(client, item)
            parent_existed = bool(parent_key)
            collection_keys = _collection_keys_for_item(item, key_by_path)
            item_body = _parent_body(item)
            item_body["collections"] = collection_keys
            if parent_key:
                response = client.patch_item(
                    parent_key,
                    {
                        "collections": collection_keys,
                        "tags": item_body["tags"],
                    },
                )
                events.append(
                    {
                        "event": "parent-item-updated",
                        "itemKey": parent_key,
                        "statusCode": response.status_code,
                    }
                )
            else:
                response = client.post_items([item_body])
                parent_key = _created_key(response.json())
                events.append(
                    {
                        "event": "parent-item-created",
                        "itemKey": parent_key,
                        "statusCode": response.status_code,
                    }
                )
            item["zotero"].update(
                {
                    "operation": "update" if parent_existed else "create",
                    "item_key": parent_key,
                    "open_uri": _zotero_open_uri(parent_key),
                    "write_executed": True,
                }
            )
            item["zotero_write_enabled"] = True
            item["final_collections"] = item.get("planned_collections") or item.get("target_collections") or []
            item["final_collection_keys"] = collection_keys
            item["final_tags"] = item.get("planned_tags") or item.get("normalized_tags") or []
            item["final_linked_pdf_path"] = str(target)
            _set_action(
                item,
                "create_or_update_zotero_item",
                True,
                item_key=parent_key,
            )
            _set_action(
                item,
                "add_to_collections",
                True,
                collection_keys=collection_keys,
                collection_names=item.get("planned_collections") or item.get("target_collections") or [],
            )
            _set_action(
                item,
                "add_tags",
                True,
                tags=item.get("planned_tags") or item.get("normalized_tags") or [],
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
            _set_action(
                item,
                "create_linked_attachment",
                True,
                parent_item_key=parent_key,
                attachment_key=attachment_key,
                linked_pdf_path=str(target),
            )
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


def build_ingest_apply_log(plan: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "apply",
        "storage_mode": StorageMode.LINKED_LOCAL.value,
        "upload_to_zotero_storage": False,
        "items": plan.get("items", []),
        "events": events,
    }


def timestamped_ingest_apply_log_path(data_dir: Path = Path("data")) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return data_dir / f"ingest_apply_log_{timestamp}.json"


def explain_ingest_plan(plan: dict[str, Any]) -> str:
    mode = plan.get("mode", "dry-run")
    lines = [
        "# ingest explanation",
        "",
        f"- Mode: {mode}",
        f"- Storage mode: {plan.get('storage_mode', StorageMode.LINKED_LOCAL.value)}",
        f"- Upload to Zotero Storage: {str(plan.get('upload_to_zotero_storage', False)).lower()}",
        "",
    ]
    for index, item in enumerate(plan.get("items", []), start=1):
        zotero = item.get("zotero") or {}
        lines.extend(
            [
                f"## {index}. {item.get('title') or Path(str(item.get('source_file', 'paper'))).stem}",
                "",
                f"- Source: {item.get('source_file') or item.get('source_path')}",
                f"- Planned vault path: {item.get('planned_vault_path') or item.get('target_path')}",
                f"- Planned Zotero collections: {', '.join(item.get('planned_collections') or item.get('target_collections') or []) or 'none'}",
                f"- Planned tags: {', '.join(item.get('planned_tags') or item.get('normalized_tags') or []) or 'none'}",
                f"- Zotero operation: {zotero.get('operation') or item.get('zotero_action') or 'none'}",
                f"- Zotero write executed: {str(bool(zotero.get('write_executed'))).lower()}",
                "",
            ]
        )
        if zotero.get("item_key"):
            lines.append(f"- Zotero item key: {zotero['item_key']}")
        if item.get("final_linked_pdf_path"):
            lines.append(f"- Final linked PDF path: {item['final_linked_pdf_path']}")
        if item.get("errors"):
            lines.append(f"- Errors: {item['errors']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
