from __future__ import annotations

import re
from pathlib import Path

from paperflow.migration_models import EnrichedZoteroItem
from paperflow.models import ZoteroItem
from paperflow.taxonomy_v2 import normalize_doi, normalize_title
from paperflow.utils import ensure_parent_dir, read_jsonl_model, write_jsonl


DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", flags=re.IGNORECASE)
MODERN_ARXIV_ID_RE = re.compile(
    r"(?P<id>(?:\d{2})(?:0[1-9]|1[0-2])\.\d{5})(?:v\d+)?",
    flags=re.IGNORECASE,
)
EXPLICIT_MODERN_ARXIV_ID_RE = re.compile(
    r"(?P<id>(?:\d{2})(?:0[1-9]|1[0-2])\.\d{4,5})(?:v\d+)?",
    flags=re.IGNORECASE,
)
EXPLICIT_OLD_ARXIV_ID_RE = re.compile(
    r"(?P<id>[a-z-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?",
    flags=re.IGNORECASE,
)
ARXIV_DOI_RE = re.compile(
    r"^10\.48550/arxiv\.(?P<id>[^\s\"'<>]+)$",
    flags=re.IGNORECASE,
)
ARXIV_URL_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(?P<id>(?:\d{2})(?:0[1-9]|1[0-2])\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?(?:\.pdf)?",
    flags=re.IGNORECASE,
)
EXPLICIT_EXTRA_ARXIV_RE = re.compile(
    r"arxiv\s*:\s*(?P<id>(?:\d{2})(?:0[1-9]|1[0-2])\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?",
    flags=re.IGNORECASE,
)


def normalize_arxiv_id(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    value = re.sub(r"^arxiv[:/\s.]*", "", value, flags=re.IGNORECASE)
    value = value.removesuffix(".pdf")
    value = re.sub(r"v\d+$", "", value, flags=re.IGNORECASE)
    return value.lower() or None


def _valid_explicit_arxiv_id(value: str | None) -> str | None:
    normalized = normalize_arxiv_id(value)
    if not normalized:
        return None
    if EXPLICIT_MODERN_ARXIV_ID_RE.fullmatch(normalized):
        return normalized
    if EXPLICIT_OLD_ARXIV_ID_RE.fullmatch(normalized):
        return normalized
    return None


def _valid_attachment_arxiv_id(value: str | None) -> str | None:
    normalized = normalize_arxiv_id(value)
    if not normalized:
        return None
    return normalized if MODERN_ARXIV_ID_RE.fullmatch(normalized) else None


def is_arxiv_doi(value: str | None) -> bool:
    normalized = normalize_doi(value)
    return bool(normalized and ARXIV_DOI_RE.fullmatch(normalized))


def arxiv_id_from_doi(value: str | None) -> str | None:
    normalized = normalize_doi(value)
    if not normalized:
        return None
    match = ARXIV_DOI_RE.fullmatch(normalized)
    return _valid_explicit_arxiv_id(match.group("id")) if match else None


def is_arxiv_url(value: str | None) -> bool:
    return bool(value and ARXIV_URL_RE.search(value))


def arxiv_id_from_url(value: str | None) -> str | None:
    if not value:
        return None
    match = ARXIV_URL_RE.search(value)
    return _valid_explicit_arxiv_id(match.group("id")) if match else None


def arxiv_id_from_extra(value: str | None) -> str | None:
    if not value:
        return None
    match = EXPLICIT_EXTRA_ARXIV_RE.search(value)
    return _valid_explicit_arxiv_id(match.group("id")) if match else None


def arxiv_id_from_attachment_filename(value: str | None) -> str | None:
    if not value:
        return None
    filename = Path(value).name
    if DOI_RE.search(filename):
        return None
    explicit = re.search(
        r"arxiv[-_\s:.]*(?P<id>(?:\d{2})(?:0[1-9]|1[0-2])\.\d{4,5})(?:v\d+)?",
        filename,
        flags=re.IGNORECASE,
    )
    if explicit:
        return _valid_explicit_arxiv_id(explicit.group("id"))
    generic = re.search(
        r"(?<![\d.])(?P<id>(?:\d{2})(?:0[1-9]|1[0-2])\.\d{5})(?:v\d+)?(?![\d.])",
        filename,
        flags=re.IGNORECASE,
    )
    return _valid_attachment_arxiv_id(generic.group("id")) if generic else None


def detect_doi(item: ZoteroItem) -> str | None:
    values = [item.doi, item.extra, item.url, item.title]
    for value in values:
        if not value:
            continue
        match = DOI_RE.search(value)
        if match:
            return normalize_doi(match.group(0))
    return normalize_doi(item.doi)


def detect_arxiv_id(item: ZoteroItem, doi_normalized: str | None) -> str | None:
    for value in (doi_normalized, item.doi):
        arxiv_id = arxiv_id_from_doi(value)
        if arxiv_id:
            return arxiv_id

    arxiv_id = arxiv_id_from_url(item.url)
    if arxiv_id:
        return arxiv_id

    arxiv_id = arxiv_id_from_extra(item.extra)
    if arxiv_id:
        return arxiv_id

    for attachment in item.attachments:
        for value in (attachment.filename, attachment.local_path):
            arxiv_id = arxiv_id_from_attachment_filename(value)
            if arxiv_id:
                return arxiv_id
    return None


def metadata_quality_score(item: ZoteroItem, doi: str | None, arxiv_id: str | None) -> float:
    score = 0.15
    if item.title:
        score += 0.15
    if item.creators:
        score += 0.12
    if doi or arxiv_id:
        score += 0.22
    if item.abstract_note:
        score += 0.18
    if item.year:
        score += 0.08
    if item.publication_title:
        score += 0.05
    if any(attachment.is_pdf for attachment in item.attachments):
        score += 0.05
    return min(1.0, round(score, 2))


def enrich_item(item: ZoteroItem) -> EnrichedZoteroItem:
    doi_normalized = detect_doi(item)
    arxiv_id = detect_arxiv_id(item, doi_normalized)
    issues: list[str] = []
    if not doi_normalized and not arxiv_id:
        issues.append("missing-doi-or-arxiv")
    if not item.abstract_note:
        issues.append("missing-abstract")
    if not item.title:
        issues.append("missing-title")
    if not item.creators:
        issues.append("missing-creators")

    return EnrichedZoteroItem(
        **item.model_dump(by_alias=False),
        normalized_title=normalize_title(item.title),
        arxiv_id=arxiv_id,
        doi_normalized=doi_normalized,
        metadata_quality_score=metadata_quality_score(item, doi_normalized, arxiv_id),
        metadata_issues=issues,
    )


def enrich_items(items: list[ZoteroItem]) -> list[EnrichedZoteroItem]:
    return [enrich_item(item) for item in items]


def write_metadata_report(items: list[EnrichedZoteroItem], path: Path) -> None:
    ensure_parent_dir(path)
    missing_ids = [item for item in items if "missing-doi-or-arxiv" in item.metadata_issues]
    missing_abstracts = [item for item in items if "missing-abstract" in item.metadata_issues]
    low_quality = [item for item in items if item.metadata_quality_score < 0.55]
    lines = [
        "# metadata repair report",
        "",
        f"- Items processed: {len(items)}",
        f"- Missing DOI/arXiv ID: {len(missing_ids)}",
        f"- Missing abstract: {len(missing_abstracts)}",
        f"- Low metadata quality (<0.55): {len(low_quality)}",
        "",
        "## Missing DOI/arXiv ID",
        "",
    ]
    lines.extend(
        f"- {item.key} | {item.title or '(untitled)'}" for item in missing_ids
    )
    if not missing_ids:
        lines.append("- None")
    lines.extend(["", "## Missing Abstract", ""])
    lines.extend(
        f"- {item.key} | {item.title or '(untitled)'}" for item in missing_abstracts
    )
    if not missing_abstracts:
        lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def enrich_metadata_file(
    input_path: Path,
    output_path: Path,
    report_path: Path,
) -> list[EnrichedZoteroItem]:
    items = read_jsonl_model(input_path, ZoteroItem)
    enriched = enrich_items(items)
    write_jsonl(output_path, enriched)
    write_metadata_report(enriched, report_path)
    return enriched
