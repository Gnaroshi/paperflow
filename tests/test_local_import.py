from __future__ import annotations

import json
from pathlib import Path

from paperflow.local_import import (
    classify_new_local_papers,
    classify_scan_row,
    local_scan,
    match_local_to_zotero,
    plan_local_import,
)


def _pdf(path: Path, content: bytes = b"%PDF-1.4\nlocal import test\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class FakeGemini:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> dict:
        self.prompts.append(prompt)
        payload = self.payloads.pop(0)
        if "error_type" in payload:
            return {"ok": False, **payload}
        return {
            "ok": True,
            "raw": {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(payload),
                                }
                            ]
                        }
                    }
                ]
            },
        }

    def close(self) -> None:
        pass


def test_local_scan_skips_hidden_temp_zero_and_duplicate_hash(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    first = _pdf(root / "2606.18208v1.pdf")
    _pdf(root / "copy.pdf", first.read_bytes())
    _pdf(root / ".hidden.pdf")
    _pdf(root / "unfinished.pdf.crdownload")
    _pdf(root / "zero.pdf", b"")

    plan = local_scan(root, recursive=True, min_size_kb=0)

    by_name = {Path(row["path"]).name: row for row in plan["files"]}
    assert "2606.18208v1.pdf" in by_name
    duplicate_pair = [by_name["2606.18208v1.pdf"], by_name["copy.pdf"]]
    assert {row["scan_status"] for row in duplicate_pair} == {"ok", "skipped"}
    assert any(row.get("detected", {}).get("arxiv_id") == "2606.18208v1" for row in duplicate_pair)
    skipped = next(row for row in duplicate_pair if row["scan_status"] == "skipped")
    assert "duplicate-file-hash" in skipped["errors"][0]
    assert "zero.pdf" in by_name
    assert ".hidden.pdf" not in by_name
    assert "unfinished.pdf.crdownload" not in by_name


def test_match_zotero_exact_arxiv_excludes_import() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/2606.18208v1.pdf",
                "filename": "2606.18208v1.pdf",
                "scan_status": "ok",
                "sha256": "abc",
                "detected": {"arxiv_id": "2606.18208v1", "doi": None, "title": "Looped World Models", "year": 2026},
            }
        ]
    }
    index = {
        "items": [
            {
                "item_key": "ITEM1",
                "title": "Looped World Models",
                "normalized_title": "looped world models",
                "year": 2026,
                "arxiv_id": "2606.18208v1",
                "arxiv_base_id": "2606.18208",
                "doi_normalized": None,
                "attachment_sha256": [],
                "attachment_paths": [],
                "reading_work_present": True,
            }
        ]
    }

    plan = match_local_to_zotero(scan, index)

    match = plan["matches"][0]
    assert match["match_status"] == "exact_existing"
    assert match["safe_to_import"] is False
    assert match["reading_work_present_on_existing"] is True


def test_match_zotero_exact_doi_excludes_import() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/paper.pdf",
                "filename": "paper.pdf",
                "scan_status": "ok",
                "detected": {"doi": "HTTPS://doi.org/10.1109/CVPR52688.2022.01631", "title": "CV Paper", "year": 2022},
            }
        ]
    }
    index = {
        "items": [
            {
                "item_key": "ITEM1",
                "title": "CV Paper",
                "normalized_title": "cv paper",
                "year": 2022,
                "doi_normalized": "10.1109/cvpr52688.2022.01631",
                "attachment_sha256": [],
                "attachment_paths": [],
                "reading_work_present": False,
            }
        ]
    }

    match = match_local_to_zotero(scan, index)["matches"][0]

    assert match["match_status"] == "exact_existing"
    assert match["match_reason"] == "same DOI"
    assert match["safe_to_import"] is False


def test_match_zotero_newer_arxiv_version_is_review_update_candidate() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/2606.18208v2.pdf",
                "filename": "2606.18208v2.pdf",
                "scan_status": "ok",
                "detected": {"arxiv_id": "2606.18208v2", "title": "Looped World Models", "year": 2026},
            }
        ]
    }
    index = {
        "items": [
            {
                "item_key": "ITEM1",
                "title": "Looped World Models",
                "normalized_title": "looped world models",
                "year": 2026,
                "arxiv_id": "2606.18208v1",
                "arxiv_base_id": "2606.18208",
                "attachment_sha256": [],
                "attachment_paths": [],
                "reading_work_present": True,
            }
        ]
    }

    match = match_local_to_zotero(scan, index)["matches"][0]

    assert match["match_status"] == "update_candidate"
    assert match["safe_to_replace_existing_pdf"] is False
    assert match["unsafe_auto_replace"] is True
    assert match["existing_version"] == 1
    assert match["local_version"] == 2
    assert match["suggested_action"] == "attach new version or replace linked PDF after review"


def test_match_zotero_same_arxiv_base_same_family_excludes_import() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/2606.18208v1.pdf",
                "filename": "2606.18208v1.pdf",
                "scan_status": "ok",
                "detected": {"arxiv_id": "2606.18208v1", "title": "Looped World Models", "year": 2026},
            }
        ]
    }
    index = {
        "items": [
            {
                "item_key": "ITEM1",
                "title": "Looped World Models",
                "normalized_title": "looped world models",
                "year": 2026,
                "arxiv_id": "2606.18208v2",
                "attachment_sha256": [],
                "attachment_paths": [],
                "reading_work_present": False,
            }
        ]
    }

    match = match_local_to_zotero(scan, index)["matches"][0]

    assert match["match_status"] == "exact_existing"
    assert match["match_reason"] == "same arXiv base ID"


def test_match_zotero_attachment_hash_excludes_import() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/hash.pdf",
                "filename": "hash.pdf",
                "scan_status": "ok",
                "sha256": "abc123",
                "detected": {"title": "Hash Paper", "year": 2025},
            }
        ]
    }
    index = {
        "items": [
            {
                "item_key": "ITEM1",
                "title": "Hash Paper",
                "normalized_title": "hash paper",
                "year": 2025,
                "attachment_sha256": ["abc123"],
                "attachment_paths": [],
                "reading_work_present": False,
            }
        ]
    }

    match = match_local_to_zotero(scan, index)["matches"][0]

    assert match["match_status"] == "exact_existing"
    assert match["match_reason"] == "same PDF SHA256"


def test_match_zotero_resolved_attachment_path_excludes_import(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path / "paper.pdf")
    scan = {
        "files": [
            {
                "path": str(tmp_path / "subdir" / ".." / "paper.pdf"),
                "filename": "paper.pdf",
                "scan_status": "ok",
                "detected": {"title": "Path Paper", "year": 2025},
            }
        ]
    }
    index = {
        "items": [
            {
                "item_key": "ITEM1",
                "title": "Path Paper",
                "normalized_title": "path paper",
                "year": 2025,
                "attachment_sha256": [],
                "attachment_paths": [str(pdf)],
                "reading_work_present": False,
            }
        ]
    }

    match = match_local_to_zotero(scan, index)["matches"][0]

    assert match["match_status"] == "exact_existing"
    assert match["match_reason"] == "same resolved attachment local path"


def test_match_zotero_title_year_first_author_excludes_import() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/title.pdf",
                "filename": "title.pdf",
                "scan_status": "ok",
                "pdf_metadata_author": "Ada Lovelace",
                "detected": {"title": "Exact Title Match", "year": 2025},
            }
        ]
    }
    index = {
        "items": [
            {
                "item_key": "ITEM1",
                "title": "Exact Title Match",
                "normalized_title": "exact title match",
                "year": 2025,
                "first_author": "lovelace",
                "attachment_sha256": [],
                "attachment_paths": [],
                "reading_work_present": False,
            }
        ]
    }

    match = match_local_to_zotero(scan, index)["matches"][0]

    assert match["match_status"] == "exact_existing"
    assert match["match_reason"] == "same normalized title, year, and first author"


def test_fuzzy_title_without_ids_is_possible_existing_review() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/fuzzy.pdf",
                "filename": "fuzzy.pdf",
                "scan_status": "ok",
                "detected": {"title": "Looped World Model", "year": 2026},
            }
        ]
    }
    index = {
        "items": [
            {
                "item_key": "ITEM1",
                "title": "Looped World Models",
                "normalized_title": "looped world models",
                "year": 2026,
                "attachment_sha256": [],
                "attachment_paths": [],
                "reading_work_present": False,
            }
        ]
    }

    match = match_local_to_zotero(scan, index)["matches"][0]

    assert match["match_status"] == "possible_existing"
    assert match["safe_to_import"] is False


def test_taxonomy_v3_battery_paper_does_not_become_rag() -> None:
    row = {
        "filename": "battery_soh_prediction.pdf",
        "detected": {"title": "Battery State of Health and RUL Prediction", "arxiv_id": None, "year": 2025},
        "first_pages_text": "battery degradation state of health SOH RUL cycle life prediction",
    }

    classification = classify_scan_row(row)

    assert "AI Library/20 Areas/Battery ML & Prognostics/RUL & SOH Estimation" in classification["target_collections"]
    assert "AI Library/20 Areas/LLMs & Reasoning/RAG & Retrieval" not in classification["target_collections"]


def test_taxonomy_v3_explicit_rag_only_when_retrieval_present() -> None:
    row = {
        "filename": "retrieval_augmented_generation.pdf",
        "detected": {
            "title": "Retrieval-Augmented Generation with Dense Retrieval",
            "arxiv_id": None,
            "year": 2025,
        },
        "first_pages_text": "retrieval augmented generation retriever passage retrieval query-document retrieval",
    }

    classification = classify_scan_row(row)

    assert "AI Library/20 Areas/LLMs & Reasoning/RAG & Retrieval" in classification["target_collections"]


def test_taxonomy_v3_representation_learning_does_not_become_rag() -> None:
    row = {
        "filename": "simclr.pdf",
        "detected": {"title": "A Simple Framework for Contrastive Learning", "arxiv_id": None, "year": 2020},
        "first_pages_text": "SimCLR contrastive learning self-supervised representation learning. References document retrieval.",
    }

    classification = classify_scan_row(row)

    assert "AI Library/20 Areas/Representation Learning/Contrastive Learning" in classification["target_collections"]
    assert "AI Library/20 Areas/LLMs & Reasoning/RAG & Retrieval" not in classification["target_collections"]


def test_taxonomy_v3_looped_world_models_special_rule() -> None:
    row = {
        "filename": "2606.18208v1.pdf",
        "detected": {
            "title": "Looped World Models",
            "arxiv_id": "2606.18208v1",
            "year": 2026,
            "abstract_present": True,
        },
        "first_pages_text": (
            "arXiv:2606.18208v1 Looped World Models. "
            "We introduce the first looped architectures for world modelling with parameter-shared transformers."
        ),
        "first_page_abstract_candidate": "We introduce the first looped architectures for world modelling with parameter sharing.",
    }

    classification = classify_scan_row(row)

    assert classification["target_collections"][:3] == [
        "AI Library/20 Areas/World Models & Simulation/Latent World Models",
        "AI Library/20 Areas/Recurrent & Adaptive Computation/Looped Transformers",
        "AI Library/20 Areas/Efficient ML Systems/Parameter Sharing",
    ]
    assert "area/world-models" in classification["normalized_tags"]
    assert "method/looped-transformer" in classification["normalized_tags"]
    assert "source/arxiv" in classification["normalized_tags"]


def test_taxonomy_v3_low_confidence_uses_review_queue_not_inbox() -> None:
    row = {
        "filename": "unclear.pdf",
        "detected": {"title": "A Miscellaneous Note", "year": 2024, "abstract_present": True},
        "first_pages_text": "This note has no recognizable paper taxonomy evidence.",
        "first_page_abstract_candidate": "This note has no recognizable paper taxonomy evidence but has enough text to count.",
    }

    classification = classify_scan_row(row)

    assert "AI Library/05 Review Queue/Ambiguous Classification" in classification["target_collections"]
    assert "AI Library/00 Inbox" not in classification["target_collections"]
    assert "cleanup/low-confidence" in classification["normalized_tags"]
    assert classification["normalized_tags"][0] == "status/review-needed"


def test_taxonomy_v3_missing_metadata_and_abstract_add_review_collections() -> None:
    row = {
        "filename": "unknown.pdf",
        "detected": {"title": "", "arxiv_id": None, "doi": None, "year": None, "abstract_present": False},
        "first_pages_text": "unknown paper",
    }

    classification = classify_scan_row(row)

    assert "AI Library/05 Review Queue/Missing Metadata" in classification["target_collections"]
    assert "AI Library/05 Review Queue/Missing Abstract" in classification["target_collections"]
    assert "cleanup/missing-metadata" in classification["normalized_tags"]
    assert "cleanup/missing-abstract" in classification["normalized_tags"]


def test_possible_existing_goes_to_review_queue_not_import() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/paper.pdf",
                "filename": "paper.pdf",
                "scan_status": "ok",
                "detected": {"title": "Ambiguous Paper", "year": 2025},
            }
        ]
    }
    matches = {
        "matches": [
            {
                "local_path": "/tmp/paper.pdf",
                "match_status": "possible_existing",
                "matched_zotero_item_key": "ITEM1",
            }
        ]
    }

    plan = classify_new_local_papers(scan, matches)
    item = plan["items"][0]

    assert item["classification_action"] == "review"
    assert "AI Library/05 Review Queue/Possible Zotero Duplicate" in item["target_collections"]
    assert "cleanup/possible-existing" in item["normalized_tags"]


def test_local_duplicate_by_doi_prefers_clearer_metadata() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/long/downloads/copy.pdf",
                "filename": "copy.pdf",
                "scan_status": "ok",
                "size_bytes": 9000,
                "modified_at": "2026-01-02T00:00:00+00:00",
                "detected": {"doi": "10.1234/example", "title": None, "year": None, "abstract_present": False},
            },
            {
                "path": "/tmp/paper.pdf",
                "filename": "paper.pdf",
                "scan_status": "ok",
                "size_bytes": 1000,
                "modified_at": "2026-01-01T00:00:00+00:00",
                "first_page_abstract_candidate": "This paper has a clearer abstract.",
                "detected": {
                    "doi": "10.1234/example",
                    "title": "Clear Metadata Paper",
                    "year": 2025,
                    "abstract_present": True,
                },
            },
        ]
    }

    matches = match_local_to_zotero(scan, {"items": []})["matches"]
    duplicate = next(row for row in matches if row["match_status"] == "local_duplicate")

    assert duplicate["local_path"] == "/tmp/long/downloads/copy.pdf"
    assert duplicate["canonical_local_path"] == "/tmp/paper.pdf"
    assert duplicate["safe_to_import"] is False
    assert "doi:10.1234/example" in duplicate["match_reason"]


def test_local_duplicate_prefers_highest_arxiv_version_when_metadata_ties() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/2606.18208v1.pdf",
                "filename": "2606.18208v1.pdf",
                "scan_status": "ok",
                "size_bytes": 1000,
                "modified_at": "2026-01-03T00:00:00+00:00",
                "detected": {"arxiv_id": "2606.18208v1", "title": "Looped World Models", "year": 2026, "abstract_present": True},
            },
            {
                "path": "/tmp/2606.18208v2.pdf",
                "filename": "2606.18208v2.pdf",
                "scan_status": "ok",
                "size_bytes": 1000,
                "modified_at": "2026-01-01T00:00:00+00:00",
                "detected": {"arxiv_id": "2606.18208v2", "title": "Looped World Models", "year": 2026, "abstract_present": True},
            },
        ]
    }

    matches = match_local_to_zotero(scan, {"items": []})["matches"]
    duplicate = next(row for row in matches if row["match_status"] == "local_duplicate")

    assert duplicate["local_path"] == "/tmp/2606.18208v1.pdf"
    assert duplicate["canonical_local_path"] == "/tmp/2606.18208v2.pdf"
    assert "arxiv_base:2606.18208" in duplicate["match_reason"]


def test_local_duplicate_is_not_classified_for_import() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/2606.18208v1.pdf",
                "filename": "2606.18208v1.pdf",
                "scan_status": "ok",
                "detected": {"arxiv_id": "2606.18208v1", "title": "Looped World Models", "year": 2026},
            },
            {
                "path": "/tmp/2606.18208v2.pdf",
                "filename": "2606.18208v2.pdf",
                "scan_status": "ok",
                "detected": {"arxiv_id": "2606.18208v2", "title": "Looped World Models", "year": 2026},
            },
        ]
    }
    matches = match_local_to_zotero(scan, {"items": []})

    plan = classify_new_local_papers(scan, matches)

    assert len(plan["items"]) == 1
    assert plan["items"][0]["local_path"] == "/tmp/2606.18208v2.pdf"
    assert plan["items"][0]["classification_action"] == "import"


def test_local_plan_import_uses_area_year_and_linked_local(tmp_path: Path) -> None:
    source = _pdf(tmp_path / "paper.pdf")
    classification = {
        "items": [
            {
                "classification_action": "import",
                "local_path": str(source),
                "title": "Battery State of Health Prediction",
                "year": 2025,
                "doi": None,
                "arxiv_id": "2501.12345v1",
                "sha256": "abcdef123456",
                "sha256_first_1mb": "abcdef123456",
                "abstract_present": True,
                "target_collections": ["AI Library/20 Areas/Battery ML & Prognostics/RUL & SOH Estimation"],
                "normalized_tags": ["status/to-read", "area/battery-ml", "type/method"],
                "confidence": 0.8,
                "rationale": "battery prognostics signal",
                "gemini_used": False,
            }
        ]
    }

    plan = plan_local_import(classification, vault_library=tmp_path / "Library")
    item = plan["items"][0]

    assert plan["mode"] == "dry-run"
    assert plan["upload_to_zotero_storage"] is False
    assert "/Battery ML & Prognostics - RUL & SOH Estimation/2025/" in item["planned_vault_path"]
    assert item["planned_filename"].endswith("[arXiv 2501.12345v1].pdf")
    assert "paperflow/source-local-import" in item["planned_tags"]


def test_gemini_fallback_is_not_called_by_default() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/unclear.pdf",
                "filename": "unclear.pdf",
                "scan_status": "ok",
                "detected": {"title": "Unclear Paper", "year": 2025, "abstract_present": True},
                "first_pages_text": "no deterministic taxonomy evidence",
                "first_page_abstract_candidate": "no deterministic taxonomy evidence but enough text",
            }
        ]
    }
    fake = FakeGemini([])

    plan = classify_new_local_papers(scan, {"matches": []}, gemini_client=fake)

    assert plan["classification_engine"] == "deterministic"
    assert fake.prompts == []
    assert plan["items"][0]["gemini_used"] is False


def test_gemini_fallback_accepts_valid_taxonomy_json() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/ambiguous.pdf",
                "filename": "ambiguous.pdf",
                "scan_status": "ok",
                "detected": {"title": "Sparse Evidence", "year": 2025, "abstract_present": True},
                "first_pages_text": "paper with sparse evidence",
                "first_page_abstract_candidate": "paper with sparse evidence",
            }
        ]
    }
    fake = FakeGemini(
        [
            {
                "primary_collection": "AI Library/20 Areas/Vision-Language Models/Prompt Learning & Adapters",
                "secondary_collections": [],
                "tags": ["area/vlm", "method/adapter", "method/prompt-learning", "type/method", "source/local-pdf"],
                "confidence": 0.88,
                "evidence": [{"source": "abstract", "quote": "adapter method"}],
                "rationale": "The supplied evidence indicates VLM adapters.",
                "needs_review": False,
            }
        ]
    )

    plan = classify_new_local_papers(scan, {"matches": []}, use_gemini=True, gemini_client=fake)
    item = plan["items"][0]

    assert fake.prompts
    assert "Allowed collection tree" in fake.prompts[0]
    assert item["gemini_used"] is True
    assert item["target_collections"] == [
        "AI Library/20 Areas/Vision-Language Models/Prompt Learning & Adapters"
    ]
    assert "method/adapter" in item["normalized_tags"]


def test_gemini_fallback_rejects_unknown_collection() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/ambiguous.pdf",
                "filename": "ambiguous.pdf",
                "scan_status": "ok",
                "detected": {"title": "Unknown Paper", "year": 2025, "abstract_present": True},
                "first_pages_text": "no deterministic taxonomy evidence",
                "first_page_abstract_candidate": "no deterministic taxonomy evidence",
            }
        ]
    }
    fake = FakeGemini(
        [
            {
                "primary_collection": "AI Library/20 Areas/Made Up Area",
                "secondary_collections": [],
                "tags": ["area/vlm"],
                "confidence": 0.91,
                "evidence": [],
                "rationale": "invalid",
                "needs_review": False,
            }
        ]
    )

    plan = classify_new_local_papers(scan, {"matches": []}, use_gemini=True, gemini_client=fake)
    item = plan["items"][0]

    assert item["gemini_used"] is False
    assert item["gemini_rejected"] is True
    assert "AI Library/05 Review Queue/Ambiguous Classification" in item["target_collections"]
    assert "unknown primary collection" in item["gemini_rejection_reason"]


def test_gemini_quota_stops_batch_and_writes_partial_plan() -> None:
    scan = {
        "files": [
            {
                "path": "/tmp/first.pdf",
                "filename": "first.pdf",
                "scan_status": "ok",
                "detected": {"title": "First", "year": 2025, "abstract_present": True},
                "first_pages_text": "unclear",
                "first_page_abstract_candidate": "unclear",
            },
            {
                "path": "/tmp/second.pdf",
                "filename": "second.pdf",
                "scan_status": "ok",
                "detected": {"title": "Second", "year": 2025, "abstract_present": True},
                "first_pages_text": "unclear",
                "first_page_abstract_candidate": "unclear",
            },
        ]
    }
    fake = FakeGemini(
        [
            {
                "error_type": "rate_limited",
                "message": "Gemini quota/rate limit reached",
            }
        ]
    )

    plan = classify_new_local_papers(
        scan,
        {"matches": []},
        use_gemini=True,
        gemini_client=fake,
        stop_on_gemini_quota=True,
    )

    assert plan["partial"] is True
    assert plan["gemini"]["stopped_due_to_quota"] is True
    assert len(plan["items"]) == 1
    assert plan["items"][0]["classification_action"] == "review"
