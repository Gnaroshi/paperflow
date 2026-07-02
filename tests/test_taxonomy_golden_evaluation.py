from __future__ import annotations

from paperflow.local_import import classify_scan_row
from paperflow.taxonomy_overrides import evaluate_golden_classifications


RAG_COLLECTION = "AI Library/20 Areas/LLMs & Reasoning/RAG & Retrieval"


def _evaluate(entry: dict) -> dict:
    return evaluate_golden_classifications([entry], classify_scan_row)["results"][0]


def _entry(
    title: str,
    text: str,
    expected_collections: list[str],
    expected_tags: list[str] | None = None,
    forbidden_collections: list[str] | None = None,
    forbidden_tags: list[str] | None = None,
    **extra,
) -> dict:
    return {
        "id": extra.pop("id", title),
        "title": title,
        "text": text,
        "expected_collections": expected_collections,
        "expected_tags": expected_tags or [],
        "forbidden_collections": forbidden_collections or [RAG_COLLECTION],
        "forbidden_tags": forbidden_tags or ["method/rag"],
        "abstract_present": True,
        "year": extra.pop("year", 2025),
        **extra,
    }


def test_golden_looped_world_models_goes_to_world_models_and_recurrent() -> None:
    result = _evaluate(
        _entry(
            "Looped World Models",
            "arXiv:2606.18208v1. We introduce the first looped architectures for world modelling with parameter-shared transformers.",
            [
                "AI Library/20 Areas/World Models & Simulation/Latent World Models",
                "AI Library/20 Areas/Recurrent & Adaptive Computation/Looped Transformers",
            ],
            [
                "area/world-models",
                "area/recurrent-adaptive-computation",
                "method/world-model",
                "method/looped-transformer",
                "method/adaptive-computation",
                "source/arxiv",
            ],
            id="2606.18208v1",
            arxiv_id="2606.18208v1",
            url="https://arxiv.org/abs/2606.18208v1",
            year=2026,
        )
    )

    assert result["ok"] is True


def test_golden_battery_degradation_goes_to_battery_ml() -> None:
    result = _evaluate(
        _entry(
            "Battery degradation and cycle life prediction",
            "lithium-ion battery degradation cycle life state of health SOH remaining useful life RUL prediction",
            ["AI Library/20 Areas/Battery ML & Prognostics"],
            ["area/battery-ml"],
        )
    )

    assert result["ok"] is True


def test_golden_fixmatch_goes_to_representation_learning_not_rag() -> None:
    result = _evaluate(
        _entry(
            "FixMatch: Simplifying Semi-Supervised Learning with Consistency and Confidence",
            "FixMatch semi-supervised learning representation learning data augmentation. References document retrieval.",
            [
                "AI Library/20 Areas/Representation Learning/Semi-Supervised Learning",
                "AI Library/30 Resources/Foundational Papers",
            ],
            ["area/representation-learning", "method/semi-supervised-learning"],
        )
    )

    assert result["ok"] is True


def test_golden_simclr_goes_to_representation_learning_not_rag() -> None:
    result = _evaluate(
        _entry(
            "A Simple Framework for Contrastive Learning of Visual Representations",
            "SimCLR contrastive learning self-supervised representation learning.",
            [
                "AI Library/20 Areas/Representation Learning/Contrastive Learning",
                "AI Library/30 Resources/Foundational Papers",
            ],
            ["area/representation-learning", "method/contrastive-learning"],
        )
    )

    assert result["ok"] is True


def test_golden_neural_ode_goes_to_time_series_foundational_not_inbox() -> None:
    result = _evaluate(
        _entry(
            "Neural Ordinary Differential Equations",
            "Neural ODE continuous-depth models dynamical systems controlled differential equations.",
            [
                "AI Library/20 Areas/Time-Series & Dynamical Systems/Neural ODEs & CDEs",
                "AI Library/30 Resources/Foundational Papers",
            ],
            ["area/time-series", "method/neural-ode", "type/foundational"],
            forbidden_collections=["AI Library/00 Inbox", RAG_COLLECTION],
        )
    )

    assert result["ok"] is True


def test_golden_yolo_faster_rcnn_fpn_go_to_object_detection_foundational() -> None:
    for title, text in [
        ("YOLO: You Only Look Once", "YOLO you only look once object detection bounding boxes."),
        ("Faster R-CNN", "Faster R-CNN object detection region proposal networks."),
        ("Feature Pyramid Networks for Object Detection", "FPN feature pyramid networks object detection."),
    ]:
        result = _evaluate(
            _entry(
                title,
                text,
                [
                    "AI Library/20 Areas/Computer Vision/Object Detection",
                    "AI Library/30 Resources/Foundational Papers",
                ],
                ["area/classic-cv", "task/object-detection", "type/foundational"],
            )
        )
        assert result["ok"] is True


def test_golden_cotracker_raft3d_go_to_tracking_and_3d_vision() -> None:
    cotracker = _evaluate(
        _entry(
            "CoTracker: It is Better to Track Together",
            "CoTracker point tracking correspondence across video frames.",
            ["AI Library/20 Areas/Computer Vision/Tracking & Correspondence"],
            ["area/classic-cv", "task/tracking"],
        )
    )
    raft3d = _evaluate(
        _entry(
            "RAFT-3D: Scene Flow using Rigid-Motion Embeddings",
            "RAFT-3D scene flow 3D vision 3D motion reconstruction.",
            ["AI Library/20 Areas/Computer Vision/Scene Flow & 3D Vision"],
            ["area/classic-cv", "task/scene-flow"],
        )
    )

    assert cotracker["ok"] is True
    assert raft3d["ok"] is True


def test_golden_libero_goes_to_vla_robot_benchmarks() -> None:
    result = _evaluate(
        _entry(
            "LIBERO: Benchmarking Knowledge Transfer for Lifelong Robot Learning",
            "LIBERO robot benchmarks robot manipulation imitation learning policy learning.",
            ["AI Library/20 Areas/Vision-Language-Action & Robotics/Robot Benchmarks"],
            ["area/vla-robotics", "type/benchmark"],
        )
    )

    assert result["ok"] is True


def test_golden_conditional_prompt_learning_goes_to_vlm_prompt_not_arxiv_without_url() -> None:
    result = _evaluate(
        _entry(
            "Conditional Prompt Learning for Vision-Language Models",
            "Conditional prompt learning for vision-language models with prompt adapters.",
            ["AI Library/20 Areas/Vision-Language Models/Prompt Learning & Adapters"],
            ["area/vlm", "method/prompt-learning", "method/adapter"],
            forbidden_tags=["source/arxiv", "method/rag"],
        )
    )

    assert result["ok"] is True


def test_golden_ieee_doi_fragment_does_not_create_fake_arxiv_id() -> None:
    result = _evaluate(
        _entry(
            "A CVPR Object Detection Paper",
            "Object detection with convolutional neural networks.",
            ["AI Library/20 Areas/Computer Vision/Object Detection"],
            ["source/conference"],
            forbidden_tags=["source/arxiv", "method/rag"],
            doi="10.1109/CVPR52688.2022.01631",
            year=2022,
        )
    )

    assert result["ok"] is True
