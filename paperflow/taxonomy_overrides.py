from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

from paperflow.taxonomy_v3 import COLLECTION_TREE_V3, TAG_SET_V3, unique_preserve_order
from paperflow.utils import dump_json_data, ensure_parent_dir


DEFAULT_OVERRIDES_PATH = Path("config/user_taxonomy_overrides.yaml")
DEFAULT_GOLDEN_SET_PATH = Path("data/taxonomy_golden_set.json")
DEFAULT_EVALUATION_JSON_PATH = Path("data/taxonomy_evaluation.json")
DEFAULT_EVALUATION_REPORT_PATH = Path("data/taxonomy_evaluation.md")
DEFAULT_GOLDEN_CLASSIFICATIONS_PATH = Path("data/golden_classifications.yaml")
DEFAULT_GOLDEN_EVALUATION_JSON_PATH = Path("data/golden_evaluation.json")
DEFAULT_GOLDEN_EVALUATION_REPORT_PATH = Path("data/golden_evaluation.md")

CONDITION_KEYS = {
    "title_contains",
    "title_contains_any",
    "abstract_contains",
    "abstract_contains_any",
    "text_contains",
    "text_contains_any",
    "filename_contains",
    "filename_contains_any",
    "venue_contains",
    "venue_contains_any",
    "keywords_contains",
    "keywords_contains_any",
    "existing_tags_contains",
    "existing_tags_contains_any",
}


def default_overrides_path() -> Path:
    return Path(os.environ.get("PAPERFLOW_TAXONOMY_OVERRIDES", str(DEFAULT_OVERRIDES_PATH)))


def allowed_collection_paths_v3() -> set[str]:
    allowed: set[str] = set()
    for path in COLLECTION_TREE_V3:
        parts = path.split("/")
        for index in range(1, len(parts) + 1):
            allowed.add("/".join(parts[:index]))
    return allowed


def load_user_taxonomy_overrides(path: Path | None = None) -> dict[str, Any]:
    resolved = path or default_overrides_path()
    if not resolved.exists():
        return {"rules": []}
    data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{resolved} must contain a YAML mapping with a rules list.")
    rules = data.get("rules", [])
    if rules is None:
        rules = []
    if not isinstance(rules, list):
        raise ValueError(f"{resolved}: rules must be a list.")
    data["rules"] = rules
    return data


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _contains_term(text: str, term: str) -> bool:
    if not text or not term:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(term.lower()).replace(r"\ ", r"[\s\-]+") + r"(?![a-z0-9])"
    return bool(re.search(pattern, text.lower()))


def _snippet(text: str, term: str) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    lowered = normalized.lower()
    index = lowered.find(term.lower())
    if index < 0:
        return term
    start = max(0, index - 70)
    end = min(len(normalized), index + len(term) + 90)
    prefix = "..." if start else ""
    suffix = "..." if end < len(normalized) else ""
    return f"{prefix}{normalized[start:end].strip()}{suffix}"


def _evidence_text(evidence: dict[str, Any], key: str) -> str:
    match key:
        case "title":
            return str(evidence.get("title") or "")
        case "abstract":
            return str(evidence.get("abstract") or "")
        case "filename":
            return str(evidence.get("filename") or "")
        case "venue":
            return str(evidence.get("venue") or "")
        case "keywords":
            return str(evidence.get("keywords") or "")
        case "existing_tags":
            return str(evidence.get("existing_tags") or "")
        case _:
            return str(evidence.get("main_text") or evidence.get("full_text") or "")


def _match_terms(text: str, terms: list[str], require_all: bool) -> tuple[bool, list[str]]:
    matches = [term for term in terms if _contains_term(text, term)]
    if not terms:
        return False, []
    return (len(matches) == len(terms) if require_all else bool(matches), matches)


def rule_matches_evidence(rule: dict[str, Any], evidence: dict[str, Any]) -> tuple[bool, list[str], str]:
    conditions = rule.get("when") or {}
    if not isinstance(conditions, dict) or not conditions:
        return False, [], ""

    matched_terms: list[str] = []
    snippet_source = str(evidence.get("main_text") or evidence.get("full_text") or "")
    for condition_key, raw_terms in conditions.items():
        terms = _string_list(raw_terms)
        if condition_key.endswith("_contains_any"):
            evidence_key = condition_key.removesuffix("_contains_any")
            ok, matches = _match_terms(_evidence_text(evidence, evidence_key), terms, require_all=False)
        elif condition_key.endswith("_contains"):
            evidence_key = condition_key.removesuffix("_contains")
            ok, matches = _match_terms(_evidence_text(evidence, evidence_key), terms, require_all=True)
        else:
            return False, [], ""
        if not ok:
            return False, [], ""
        matched_terms.extend(matches)
        if matches and condition_key.startswith(("title_", "abstract_")):
            snippet_source = _evidence_text(evidence, condition_key.split("_contains", maxsplit=1)[0])

    return True, unique_preserve_order(matched_terms), snippet_source


def override_candidates_for_evidence(evidence: dict[str, Any], path: Path | None = None) -> list[dict[str, Any]]:
    overrides = load_user_taxonomy_overrides(path)
    allowed_collections = allowed_collection_paths_v3()
    candidates: list[dict[str, Any]] = []
    for rule in overrides.get("rules", []):
        if not isinstance(rule, dict) or rule.get("negative"):
            continue
        matched, matched_terms, snippet_source = rule_matches_evidence(rule, evidence)
        if not matched:
            continue
        collections = [
            collection
            for collection in _string_list(rule.get("collections"))
            if collection in allowed_collections
        ]
        tags = [tag for tag in _string_list(rule.get("tags")) if tag in TAG_SET_V3]
        if not collections and not tags:
            continue
        score = float(rule.get("confidence", 0.96) or 0.96)
        score = min(0.99, max(0.55, score))
        for collection in collections:
            candidates.append(
                {
                    "collection": collection,
                    "score": score,
                    "tags": tags,
                    "reason": f"user override: {rule.get('name') or 'unnamed rule'}",
                    "matched_terms": matched_terms,
                    "evidence_snippet": _snippet(snippet_source, matched_terms[0] if matched_terms else str(rule.get("name") or "")),
                }
            )
    return candidates


def rag_unless_contains_terms(path: Path | None = None) -> tuple[str, ...]:
    overrides = load_user_taxonomy_overrides(path)
    terms: list[str] = []
    for rule in overrides.get("rules", []):
        if not isinstance(rule, dict):
            continue
        negative = rule.get("negative") or {}
        if isinstance(negative, dict):
            terms.extend(_string_list(negative.get("rag_unless_contains_any")))
    return tuple(unique_preserve_order(term.lower() for term in terms if term.strip()))


def validate_user_taxonomy_overrides(path: Path | None = None) -> dict[str, Any]:
    resolved = path or default_overrides_path()
    errors: list[str] = []
    try:
        overrides = load_user_taxonomy_overrides(resolved)
    except Exception as exc:
        return {"ok": False, "path": str(resolved), "rule_count": 0, "errors": [str(exc)]}

    allowed_collections = allowed_collection_paths_v3()
    rules = overrides.get("rules", [])
    for index, rule in enumerate(rules):
        label = f"rules[{index}]"
        if not isinstance(rule, dict):
            errors.append(f"{label} must be a mapping.")
            continue
        if not str(rule.get("name") or "").strip():
            errors.append(f"{label} is missing name.")
        positive = rule.get("when")
        negative = rule.get("negative")
        if positive and negative:
            errors.append(f"{label} must not contain both when and negative.")
        if not positive and not negative:
            errors.append(f"{label} must contain when or negative.")
        if positive is not None:
            if not isinstance(positive, dict):
                errors.append(f"{label}.when must be a mapping.")
            else:
                for condition_key, raw_terms in positive.items():
                    if condition_key not in CONDITION_KEYS:
                        errors.append(f"{label}.when.{condition_key} is not supported.")
                    if not _string_list(raw_terms):
                        errors.append(f"{label}.when.{condition_key} must contain at least one term.")
            for collection in _string_list(rule.get("collections")):
                if collection not in allowed_collections:
                    errors.append(f"{label}.collections contains unknown collection: {collection}")
            for tag in _string_list(rule.get("tags")):
                if tag not in TAG_SET_V3:
                    errors.append(f"{label}.tags contains unknown tag: {tag}")
        if negative is not None:
            if not isinstance(negative, dict):
                errors.append(f"{label}.negative must be a mapping.")
            elif not _string_list(negative.get("rag_unless_contains_any")):
                errors.append(f"{label}.negative.rag_unless_contains_any must contain at least one term.")

    return {"ok": not errors, "path": str(resolved), "rule_count": len(rules), "errors": errors}


def item_key_to_scan_row(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data", item)
    creators = data.get("creators") or item.get("creators") or []
    creator_names = [
        " ".join(
            str(part)
            for part in [creator.get("firstName"), creator.get("lastName")]
            if part
        ).strip()
        for creator in creators
        if isinstance(creator, dict)
    ]
    tags = data.get("tags") or item.get("tags") or []
    tag_names = [
        tag.get("tag")
        for tag in tags
        if isinstance(tag, dict) and tag.get("tag")
    ]
    title = data.get("title") or item.get("title") or ""
    year = data.get("year") or item.get("year")
    if not year:
        match = re.search(r"\b(19|20)\d{2}\b", str(data.get("date") or item.get("date") or ""))
        year = int(match.group(0)) if match else None
    abstract = data.get("abstractNote") or item.get("abstractNote") or ""
    return {
        "path": "",
        "filename": f"{item.get('key') or data.get('key') or 'zotero-item'}.pdf",
        "pdf_metadata_author": "; ".join(name for name in creator_names if name),
        "publicationTitle": data.get("publicationTitle") or item.get("publicationTitle") or "",
        "abstract": abstract,
        "first_page_abstract_candidate": abstract,
        "first_pages_text": "\n".join(
            value
            for value in [
                title,
                abstract,
                data.get("publicationTitle") or item.get("publicationTitle") or "",
                data.get("url") or item.get("url") or "",
                " ".join(str(tag) for tag in tag_names),
            ]
            if value
        ),
        "detected": {
            "title": title,
            "doi": data.get("DOI") or item.get("doi_normalized") or item.get("DOI"),
            "arxiv_id": item.get("arxiv_id") or data.get("arxiv_id"),
            "year": year,
            "abstract_present": bool(str(abstract).strip()),
            "abstractNote": abstract,
            "publicationTitle": data.get("publicationTitle") or item.get("publicationTitle") or "",
            "existing_tags": tag_names,
        },
    }


def read_jsonl_dicts(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
    return rows


def find_zotero_item_for_explain(item_key: str, paths: list[Path] | None = None) -> dict[str, Any] | None:
    for path in paths or [Path("data/zotero_items_enriched.jsonl"), Path("data/zotero_items.jsonl")]:
        if not path.exists():
            continue
        for row in read_jsonl_dicts(path):
            data = row.get("data", row)
            if row.get("key") == item_key or data.get("key") == item_key:
                return row
    return None


def build_golden_set_from_files(
    scan: dict[str, Any] | None,
    classification: dict[str, Any] | None,
) -> dict[str, Any]:
    scan_by_path = {
        row.get("path"): row
        for row in (scan or {}).get("files", [])
        if isinstance(row, dict) and row.get("path")
    }
    examples: list[dict[str, Any]] = []
    for item in (classification or {}).get("items", []):
        if not isinstance(item, dict):
            continue
        path = item.get("local_path")
        scan_row = scan_by_path.get(path, {})
        examples.append(
            {
                "id": path or item.get("title"),
                "title": item.get("title"),
                "local_path": path,
                "scan_row": scan_row,
                "expected_collections": item.get("target_collections", []),
                "expected_tags": item.get("normalized_tags", []),
                "expected_confidence": item.get("confidence"),
                "rationale": item.get("rationale"),
            }
        )
    return {
        "schema_version": "1.0",
        "source_scan": "data/local_scan.json" if scan is not None else None,
        "source_classification": "data/local_classification_plan.json" if classification is not None else None,
        "examples": examples,
    }


def evaluate_golden_set(golden_set: dict[str, Any], classifier: Any) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    passed = 0
    for example in golden_set.get("examples", []):
        scan_row = example.get("scan_row") or {
            "filename": Path(str(example.get("local_path") or "paper.pdf")).name,
            "detected": {
                "title": example.get("title"),
                "abstract_present": True,
            },
            "first_pages_text": example.get("title") or "",
        }
        actual = classifier(scan_row)
        expected_collections = set(example.get("expected_collections") or [])
        expected_tags = set(example.get("expected_tags") or [])
        actual_collections = set(actual.get("target_collections") or [])
        actual_tags = set(actual.get("normalized_tags") or [])
        collections_ok = expected_collections.issubset(actual_collections)
        tags_ok = expected_tags.issubset(actual_tags)
        ok = collections_ok and tags_ok
        passed += int(ok)
        rows.append(
            {
                "id": example.get("id"),
                "title": example.get("title"),
                "ok": ok,
                "missing_collections": sorted(expected_collections - actual_collections),
                "missing_tags": sorted(expected_tags - actual_tags),
                "actual_collections": actual.get("target_collections", []),
                "actual_tags": actual.get("normalized_tags", []),
                "actual_confidence": actual.get("confidence"),
                "actual_rationale": actual.get("rationale"),
            }
        )
    total = len(rows)
    return {
        "schema_version": "1.0",
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 1.0,
        "results": rows,
    }


def write_taxonomy_evaluation_report(evaluation: dict[str, Any], path: Path = DEFAULT_EVALUATION_REPORT_PATH) -> None:
    ensure_parent_dir(path)
    lines = [
        "# taxonomy golden-set evaluation",
        "",
        f"- Total: {evaluation.get('total', 0)}",
        f"- Passed: {evaluation.get('passed', 0)}",
        f"- Failed: {evaluation.get('failed', 0)}",
        f"- Pass rate: {evaluation.get('pass_rate', 1.0):.2%}",
        "",
    ]
    failed = [row for row in evaluation.get("results", []) if not row.get("ok")]
    if failed:
        lines.append("## failures")
        lines.append("")
        for row in failed:
            lines.extend(
                [
                    f"### {row.get('title') or row.get('id')}",
                    "",
                    f"- Missing collections: {', '.join(row.get('missing_collections') or []) or 'none'}",
                    f"- Missing tags: {', '.join(row.get('missing_tags') or []) or 'none'}",
                    f"- Actual collections: {', '.join(row.get('actual_collections') or []) or 'none'}",
                    f"- Actual tags: {', '.join(row.get('actual_tags') or []) or 'none'}",
                    "",
                ]
            )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_golden_set(path: Path, data: dict[str, Any]) -> None:
    dump_json_data(path, data)


def load_golden_classifications(path: Path = DEFAULT_GOLDEN_CLASSIFICATIONS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a YAML list of golden classification entries.")
    entries: list[dict[str, Any]] = []
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}[{index}] must be a mapping.")
        entries.append(entry)
    return entries


def write_golden_classifications(path: Path, entries: list[dict[str, Any]]) -> None:
    ensure_parent_dir(path)
    path.write_text(yaml.safe_dump(entries, sort_keys=False, allow_unicode=True), encoding="utf-8")


def golden_id_from_row(row: dict[str, Any], fallback: str) -> str:
    detected = row.get("detected") or {}
    for key in ("arxiv_id", "doi"):
        value = detected.get(key)
        if value:
            return str(value)
    path = row.get("path")
    if path:
        return Path(str(path)).stem
    return fallback


def golden_entry_from_classification(
    target: str,
    row: dict[str, Any],
    classification: dict[str, Any],
    target_type: str,
) -> dict[str, Any]:
    detected = row.get("detected") or {}
    entry = {
        "id": golden_id_from_row(row, target),
        "title": detected.get("title") or row.get("pdf_metadata_title") or Path(str(row.get("filename") or target)).stem,
        "expected_collections": classification.get("target_collections", []),
        "expected_tags": classification.get("normalized_tags", []),
        "forbidden_collections": [],
        "forbidden_tags": [],
        "expected_confidence_min": classification.get("confidence"),
    }
    if target_type == "pdf" and row.get("path"):
        entry["source_path"] = row["path"]
    elif target_type == "zotero_item":
        entry["item_key"] = target
    if detected.get("doi"):
        entry["doi"] = detected["doi"]
    if detected.get("arxiv_id"):
        entry["arxiv_id"] = detected["arxiv_id"]
    if detected.get("year"):
        entry["year"] = detected["year"]
    return entry


def upsert_golden_classification(path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    entries = load_golden_classifications(path)
    replaced = False
    output: list[dict[str, Any]] = []
    for existing in entries:
        if str(existing.get("id")) == str(entry.get("id")):
            output.append(entry)
            replaced = True
        else:
            output.append(existing)
    if not replaced:
        output.append(entry)
    write_golden_classifications(path, output)
    return {"path": str(path), "id": entry.get("id"), "count": len(output), "updated": replaced}


def golden_entry_to_scan_row(entry: dict[str, Any]) -> dict[str, Any]:
    title = str(entry.get("title") or entry.get("id") or "")
    abstract = str(entry.get("abstract") or entry.get("text") or "")
    text = "\n".join(
        value
        for value in [
            title,
            abstract,
            str(entry.get("venue") or ""),
            str(entry.get("url") or ""),
            str(entry.get("doi") or ""),
        ]
        if value
    )
    return {
        "path": entry.get("source_path") or "",
        "filename": f"{entry.get('id') or 'golden'}.pdf",
        "publicationTitle": entry.get("venue") or entry.get("publicationTitle") or "",
        "abstract": abstract,
        "first_page_abstract_candidate": abstract,
        "first_pages_text": text,
        "detected": {
            "title": title,
            "doi": entry.get("doi"),
            "arxiv_id": entry.get("arxiv_id"),
            "year": entry.get("year"),
            "url": entry.get("url"),
            "abstract_present": bool(abstract.strip()) or bool(entry.get("abstract_present", True)),
            "publicationTitle": entry.get("venue") or entry.get("publicationTitle") or "",
        },
    }


def _entry_list(entry: dict[str, Any], key: str) -> list[str]:
    return _string_list(entry.get(key))


def evaluate_golden_classifications(
    entries: list[dict[str, Any]],
    classifier: Any,
    row_builder: Any | None = None,
) -> dict[str, Any]:
    row_builder = row_builder or golden_entry_to_scan_row
    results: list[dict[str, Any]] = []
    exact_collection_matches = 0
    partial_collection_matches = 0
    high_confidence_regressions = 0
    low_confidence_matches = 0

    for entry in entries:
        row = row_builder(entry)
        classification = classifier(row)
        actual_collections = classification.get("target_collections") or []
        actual_tags = classification.get("normalized_tags") or []
        expected_collections = _entry_list(entry, "expected_collections")
        expected_tags = _entry_list(entry, "expected_tags")
        forbidden_collections = _entry_list(entry, "forbidden_collections")
        forbidden_tags = _entry_list(entry, "forbidden_tags")

        actual_collection_set = set(actual_collections)
        actual_tag_set = set(actual_tags)
        expected_collection_set = set(expected_collections)
        expected_tag_set = set(expected_tags)

        exact_collection_match = actual_collection_set == expected_collection_set if expected_collections else False
        partial_collection_match = expected_collection_set.issubset(actual_collection_set) if expected_collections else True
        missing_expected_collections = sorted(expected_collection_set - actual_collection_set)
        unexpected_collections = sorted(actual_collection_set - expected_collection_set)
        missing_expected_tags = sorted(expected_tag_set - actual_tag_set)
        forbidden_collections_present = sorted(set(forbidden_collections) & actual_collection_set)
        forbidden_tags_present = sorted(set(forbidden_tags) & actual_tag_set)
        confidence = float(classification.get("confidence") or 0.0)
        expected_min = entry.get("expected_confidence_min")
        expected_min = float(expected_min) if expected_min is not None else 0.75
        confidence_calibration = "ok"
        regression = bool(
            missing_expected_collections
            or missing_expected_tags
            or forbidden_collections_present
            or forbidden_tags_present
        )
        if regression and confidence >= 0.75:
            confidence_calibration = "high_confidence_regression"
            high_confidence_regressions += 1
        elif not regression and confidence < expected_min:
            confidence_calibration = "low_confidence_match"
            low_confidence_matches += 1

        exact_collection_matches += int(exact_collection_match)
        partial_collection_matches += int(partial_collection_match)
        results.append(
            {
                "id": entry.get("id"),
                "title": entry.get("title"),
                "ok": not regression,
                "exact_collection_match": exact_collection_match,
                "partial_collection_match": partial_collection_match,
                "expected_collections": expected_collections,
                "actual_collections": actual_collections,
                "missing_expected_collections": missing_expected_collections,
                "unexpected_collections": unexpected_collections,
                "expected_tags": expected_tags,
                "actual_tags": actual_tags,
                "missing_expected_tags": missing_expected_tags,
                "forbidden_collections_present": forbidden_collections_present,
                "forbidden_tags_present": forbidden_tags_present,
                "confidence": confidence,
                "expected_confidence_min": expected_min,
                "confidence_calibration": confidence_calibration,
                "rationale": classification.get("rationale"),
            }
        )

    regression_count = sum(1 for result in results if not result["ok"])
    total = len(results)
    return {
        "schema_version": "1.0",
        "golden_set": str(DEFAULT_GOLDEN_CLASSIFICATIONS_PATH),
        "total": total,
        "exact_collection_matches": exact_collection_matches,
        "partial_collection_matches": partial_collection_matches,
        "regression_count": regression_count,
        "high_confidence_regressions": high_confidence_regressions,
        "low_confidence_matches": low_confidence_matches,
        "pass_rate": round((total - regression_count) / total, 4) if total else 1.0,
        "results": results,
    }


def write_golden_evaluation_report(
    evaluation: dict[str, Any],
    path: Path = DEFAULT_GOLDEN_EVALUATION_REPORT_PATH,
) -> None:
    ensure_parent_dir(path)
    lines = [
        "# golden classification evaluation",
        "",
        f"- Total: {evaluation.get('total', 0)}",
        f"- Exact collection matches: {evaluation.get('exact_collection_matches', 0)}",
        f"- Partial collection matches: {evaluation.get('partial_collection_matches', 0)}",
        f"- Regression count: {evaluation.get('regression_count', 0)}",
        f"- High-confidence regressions: {evaluation.get('high_confidence_regressions', 0)}",
        f"- Low-confidence matches: {evaluation.get('low_confidence_matches', 0)}",
        f"- Pass rate: {evaluation.get('pass_rate', 1.0):.2%}",
        "",
        "## results",
        "",
    ]
    for result in evaluation.get("results", []):
        status = "PASS" if result.get("ok") else "REGRESSION"
        lines.extend(
            [
                f"### {status}: {result.get('title') or result.get('id')}",
                "",
                f"- Exact collection match: {result.get('exact_collection_match')}",
                f"- Partial collection match: {result.get('partial_collection_match')}",
                f"- Missing expected tags: {', '.join(result.get('missing_expected_tags') or []) or 'none'}",
                f"- Forbidden tags present: {', '.join(result.get('forbidden_tags_present') or []) or 'none'}",
                f"- Forbidden collections present: {', '.join(result.get('forbidden_collections_present') or []) or 'none'}",
                f"- Confidence: {result.get('confidence', 0):.2f}",
                f"- Confidence calibration: {result.get('confidence_calibration')}",
                f"- Regression: {not result.get('ok')}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
