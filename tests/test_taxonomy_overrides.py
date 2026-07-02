from __future__ import annotations

from pathlib import Path

from paperflow.local_import import classify_scan_row
from paperflow.taxonomy_overrides import (
    build_golden_set_from_files,
    evaluate_golden_set,
    validate_user_taxonomy_overrides,
)


def test_user_override_adds_collection_and_tags(tmp_path: Path, monkeypatch) -> None:
    overrides = tmp_path / "overrides.yaml"
    overrides.write_text(
        """
rules:
  - name: "custom graph override"
    when:
      title_contains:
        - "magic graph"
    collections:
      - "AI Library/20 Areas/Graph Learning/Knowledge Graphs"
    tags:
      - area/graph-learning
      - method/knowledge-graph
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("PAPERFLOW_TAXONOMY_OVERRIDES", str(overrides))

    classification = classify_scan_row(
        {
            "filename": "magic_graph.pdf",
            "detected": {"title": "Magic Graph Retrieval-Free Embeddings", "year": 2026, "abstract_present": True},
            "first_pages_text": "A paper about magic graph embeddings.",
            "first_page_abstract_candidate": "A paper about magic graph embeddings.",
        }
    )

    assert "AI Library/20 Areas/Graph Learning/Knowledge Graphs" in classification["target_collections"]
    assert "area/graph-learning" in classification["normalized_tags"]
    assert "method/knowledge-graph" in classification["normalized_tags"]
    assert "user override: custom graph override" in classification["rationale"]


def test_user_negative_rag_override_blocks_vector_index_false_positive(tmp_path: Path, monkeypatch) -> None:
    overrides = tmp_path / "overrides.yaml"
    overrides.write_text(
        """
rules:
  - name: "No false RAG"
    negative:
      rag_unless_contains_any:
        - "retrieval-augmented generation"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("PAPERFLOW_TAXONOMY_OVERRIDES", str(overrides))

    classification = classify_scan_row(
        {
            "filename": "vector_index_representation.pdf",
            "detected": {"title": "Vector Index Representations", "year": 2026, "abstract_present": True},
            "first_pages_text": "We learn vector index representations for contrastive learning without document retrieval.",
            "first_page_abstract_candidate": "We learn vector index representations for contrastive learning without document retrieval.",
        }
    )

    assert "AI Library/20 Areas/LLMs & Reasoning/RAG & Retrieval" not in classification["target_collections"]


def test_user_taxonomy_override_validation_rejects_unknown_tag(tmp_path: Path) -> None:
    overrides = tmp_path / "overrides.yaml"
    overrides.write_text(
        """
rules:
  - name: "bad tag"
    when:
      title_contains:
        - "paper"
    collections:
      - "AI Library/20 Areas/Graph Learning"
    tags:
      - method/not-real
""",
        encoding="utf-8",
    )

    result = validate_user_taxonomy_overrides(overrides)

    assert result["ok"] is False
    assert any("method/not-real" in error for error in result["errors"])


def test_taxonomy_golden_set_evaluation_detects_pass(tmp_path: Path, monkeypatch) -> None:
    overrides = tmp_path / "overrides.yaml"
    overrides.write_text("rules: []\n", encoding="utf-8")
    monkeypatch.setenv("PAPERFLOW_TAXONOMY_OVERRIDES", str(overrides))
    scan = {
        "files": [
            {
                "path": "/tmp/battery.pdf",
                "filename": "battery.pdf",
                "detected": {"title": "Battery RUL Prediction", "year": 2026, "abstract_present": True},
                "first_pages_text": "battery remaining useful life RUL state of health SOH prediction",
                "first_page_abstract_candidate": "battery remaining useful life RUL state of health SOH prediction",
            }
        ]
    }
    classification = {
        "items": [
            {
                "local_path": "/tmp/battery.pdf",
                "title": "Battery RUL Prediction",
                "target_collections": ["AI Library/20 Areas/Battery ML & Prognostics/RUL & SOH Estimation"],
                "normalized_tags": ["area/battery-ml", "task/rul-prediction"],
                "confidence": 0.88,
            }
        ]
    }

    golden = build_golden_set_from_files(scan, classification)
    evaluation = evaluate_golden_set(golden, classify_scan_row)

    assert evaluation["total"] == 1
    assert evaluation["failed"] == 0
