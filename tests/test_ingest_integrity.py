from pathlib import Path
from typing import Any

from paperflow.ingest import (
    _find_existing_parent,
    _matching_existing_parent_keys,
    apply_ingest_plan,
    classify_ingest_metadata,
    ingest_review_guidance,
    sha256_file,
)
from paperflow.taxonomy_v3 import AMBIGUOUS_CLASSIFICATION_COLLECTION
from paperflow.vault import zotero_linked_attachment_path


VLA_BENCHMARK_COLLECTION = (
    "AI Library/20 Areas/Vision-Language-Action & Robotics/Robot Benchmarks"
)
INFERENCE_COLLECTION = "AI Library/20 Areas/Efficient ML Systems/Inference Acceleration"
NEURAL_ODE_COLLECTION = (
    "AI Library/20 Areas/Time-Series & Dynamical Systems/Neural ODEs & CDEs"
)


def test_vla_inference_paper_is_not_sent_to_ambiguous_review() -> None:
    collections, tags, reasons = classify_ingest_metadata(
        {
            "title": "How Fast Can I Run My VLA? Demystifying VLA Inference Performance with VLA-Perf",
            "abstract": (
                "Vision-Language-Action models require real-time inference. "
                "VLA-Perf evaluates end-to-end latency and inference performance."
            ),
            "arxiv_id": "2602.18397v1",
        }
    )

    assert collections == [VLA_BENCHMARK_COLLECTION, INFERENCE_COLLECTION]
    assert AMBIGUOUS_CLASSIFICATION_COLLECTION not in collections
    assert {"area/vla-robotics", "area/efficient-ml", "type/benchmark"} <= set(tags)
    assert any("VLA" in reason for reason in reasons)


def test_neural_ode_and_ncde_have_deterministic_taxonomy() -> None:
    ode_collections, ode_tags, _ = classify_ingest_metadata(
        {"title": "Neural Ordinary Differential Equations"}
    )
    cde_collections, cde_tags, _ = classify_ingest_metadata(
        {"title": "Neural Controlled Differential Equations for Irregular Time Series"}
    )

    assert ode_collections == [NEURAL_ODE_COLLECTION]
    assert "method/neural-ode" in ode_tags
    assert cde_collections == [NEURAL_ODE_COLLECTION]
    assert "method/neural-cde" in cde_tags


def test_ambiguous_review_guidance_explains_reason_and_next_action() -> None:
    guidance = ingest_review_guidance(
        [AMBIGUOUS_CLASSIFICATION_COLLECTION],
        ["no strong ingest taxonomy signal"],
    )

    assert guidance["required"] is True
    assert "no strong ingest taxonomy signal" in guidance["reason"]
    assert "AI Library/20 Areas" in guidance["next_action"]
    assert len(guidance["steps"]) == 3


class _ExistingParentClient:
    def iter_top_items(self) -> list[dict[str, Any]]:
        return [
            {
                "key": "NEWER",
                "data": {
                    "itemType": "journalArticle",
                    "title": "How Fast Can I Run My VLA?",
                    "url": "https://arxiv.org/abs/2602.18397v3",
                    "dateAdded": "2026-07-15T07:10:52Z",
                },
            },
            {
                "key": "OLDER",
                "data": {
                    "itemType": "preprint",
                    "title": "How Fast Can I Run My VLA?",
                    "DOI": "10.48550/arXiv.2602.18397",
                    "dateAdded": "2026-07-15T07:04:55Z",
                },
            },
        ]


def test_existing_parent_match_normalizes_arxiv_versions_and_is_deterministic() -> None:
    plan_item = {
        "title": "How Fast Can I Run My VLA?",
        "year": 2026,
        "arxiv_id": "2602.18397v1",
    }
    client = _ExistingParentClient()
    matches = _matching_existing_parent_keys(client, plan_item)  # type: ignore[arg-type]
    key = _find_existing_parent(client, plan_item)  # type: ignore[arg-type]

    assert matches == ["OLDER", "NEWER"]
    assert key == "OLDER"


class _Response:
    status_code = 200

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self._payload = payload or {}

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class _IdempotentClient:
    def __init__(self, legacy_attachment_path: str) -> None:
        self.legacy_attachment_path = legacy_attachment_path
        self.patch_calls: list[tuple[str, dict[str, Any]]] = []
        self.post_item_calls: list[list[dict[str, Any]]] = []

    def __enter__(self) -> "_IdempotentClient":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def iter_collections(self) -> list[dict[str, Any]]:
        return []

    def iter_top_items(self) -> list[dict[str, Any]]:
        return [
            {
                "key": "PARENT",
                "data": {
                    "itemType": "journalArticle",
                    "title": "Paper",
                    "url": "https://arxiv.org/abs/2602.18397",
                    "date": "2026",
                    "dateAdded": "2026-07-15T07:04:55Z",
                },
            }
        ]

    def get_item_children(self, _: str) -> list[dict[str, Any]]:
        return [
            {
                "key": "ATTACHMENT",
                "data": {
                    "itemType": "attachment",
                    "linkMode": "linked_file",
                    "path": self.legacy_attachment_path,
                },
            }
        ]

    def patch_item(self, key: str, body: dict[str, Any]) -> _Response:
        self.patch_calls.append((key, body))
        if key == "ATTACHMENT" and "path" in body:
            self.legacy_attachment_path = body["path"]
        return _Response()

    def post_items(self, payload: list[dict[str, Any]]) -> _Response:
        self.post_item_calls.append(payload)
        return _Response({"successful": {"0": {"key": "UNEXPECTED"}}})


def test_repeated_apply_reuses_parent_and_attachment_and_repairs_legacy_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"paper")
    vault = tmp_path / "Library"
    target = vault / "2026" / "paper.pdf"
    legacy_path = zotero_linked_attachment_path(
        target,
        vault_library=vault,
        relative_to_base_directory=True,
    )
    client = _IdempotentClient(legacy_path)
    monkeypatch.setattr("paperflow.ingest.ZoteroWebClient", lambda **_: client)
    plan = {
        "vault_library": str(vault),
        "items": [
            {
                "source_path": str(source),
                "source_sha256": sha256_file(source),
                "target_path": str(target),
                "title": "Paper",
                "year": 2026,
                "arxiv_id": "2602.18397v1",
                "planned_collections": [],
                "planned_tags": ["status/to-read"],
            }
        ],
    }

    first_events = apply_ingest_plan(plan, user_id="1", api_key="key")
    second_events = apply_ingest_plan(plan, user_id="1", api_key="key")

    expected_absolute_path = str(target.resolve())
    assert client.post_item_calls == []
    assert ("ATTACHMENT", {"path": expected_absolute_path}) in client.patch_calls
    assert any(event["event"] == "linked-attachment-path-repaired" for event in first_events)
    assert any(event["event"] == "linked-attachment-reused" for event in second_events)
    assert plan["items"][0]["zotero"]["operation"] == "update"
