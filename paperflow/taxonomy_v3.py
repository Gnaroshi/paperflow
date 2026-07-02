from __future__ import annotations

import re
from collections.abc import Iterable


ROOT_COLLECTION_V3 = "AI Library"
REVIEW_QUEUE_COLLECTION = "AI Library/05 Review Queue"
AMBIGUOUS_CLASSIFICATION_COLLECTION = "AI Library/05 Review Queue/Ambiguous Classification"
POSSIBLE_ZOTERO_DUPLICATE_COLLECTION = "AI Library/05 Review Queue/Possible Zotero Duplicate"
NEW_ARXIV_VERSION_COLLECTION = "AI Library/05 Review Queue/New arXiv Version"
MISSING_METADATA_REVIEW_COLLECTION = "AI Library/05 Review Queue/Missing Metadata"
MISSING_ABSTRACT_REVIEW_COLLECTION = "AI Library/05 Review Queue/Missing Abstract"
NEEDS_MANUAL_APPROVAL_COLLECTION = "AI Library/05 Review Queue/Needs Manual Approval"

COLLECTION_TREE_V3: list[str] = [
    "AI Library/00 Inbox",
    REVIEW_QUEUE_COLLECTION,
    AMBIGUOUS_CLASSIFICATION_COLLECTION,
    POSSIBLE_ZOTERO_DUPLICATE_COLLECTION,
    NEW_ARXIV_VERSION_COLLECTION,
    MISSING_METADATA_REVIEW_COLLECTION,
    MISSING_ABSTRACT_REVIEW_COLLECTION,
    NEEDS_MANUAL_APPROVAL_COLLECTION,
    "AI Library/10 Active Reading",
    "AI Library/20 Areas/LLMs & Reasoning/Prompting & In-Context Learning",
    "AI Library/20 Areas/LLMs & Reasoning/Chain-of-Thought & Latent Reasoning",
    "AI Library/20 Areas/LLMs & Reasoning/Alignment & Safety",
    "AI Library/20 Areas/LLMs & Reasoning/Hallucination & Factuality",
    "AI Library/20 Areas/LLMs & Reasoning/Jailbreaks & Security",
    "AI Library/20 Areas/LLMs & Reasoning/Efficient LLM Inference",
    "AI Library/20 Areas/LLMs & Reasoning/KV Cache & Compression",
    "AI Library/20 Areas/LLMs & Reasoning/Distillation & Small LMs",
    "AI Library/20 Areas/LLMs & Reasoning/RAG & Retrieval",
    "AI Library/20 Areas/Vision-Language Models/CLIP-style Representation",
    "AI Library/20 Areas/Vision-Language Models/Prompt Learning & Adapters",
    "AI Library/20 Areas/Vision-Language Models/Multimodal Reasoning",
    "AI Library/20 Areas/Vision-Language Models/VLM Evaluation",
    "AI Library/20 Areas/Vision-Language Models/Medical VLMs",
    "AI Library/20 Areas/Vision-Language Models/VLM Safety & Robustness",
    "AI Library/20 Areas/Vision-Language-Action & Robotics/Generalist Robot Policies",
    "AI Library/20 Areas/Vision-Language-Action & Robotics/Robot Manipulation",
    "AI Library/20 Areas/Vision-Language-Action & Robotics/Imitation Learning",
    "AI Library/20 Areas/Vision-Language-Action & Robotics/Inverse Dynamics & Action Models",
    "AI Library/20 Areas/Vision-Language-Action & Robotics/Motion Tokenization",
    "AI Library/20 Areas/Vision-Language-Action & Robotics/Robot Benchmarks",
    "AI Library/20 Areas/Vision-Language-Action & Robotics/Embodied Agents",
    "AI Library/20 Areas/World Models & Simulation/Latent World Models",
    "AI Library/20 Areas/World Models & Simulation/Video World Models",
    "AI Library/20 Areas/World Models & Simulation/Model-Based RL",
    "AI Library/20 Areas/World Models & Simulation/Planning with Learned Models",
    "AI Library/20 Areas/World Models & Simulation/Deferred Decoding",
    "AI Library/20 Areas/World Models & Simulation/Long-Horizon Rollouts",
    "AI Library/20 Areas/World Models & Simulation/Interactive Environment Models",
    "AI Library/20 Areas/Recurrent & Adaptive Computation/Looped Transformers",
    "AI Library/20 Areas/Recurrent & Adaptive Computation/Recurrent-Depth Models",
    "AI Library/20 Areas/Recurrent & Adaptive Computation/Adaptive Computation Time",
    "AI Library/20 Areas/Recurrent & Adaptive Computation/Early Exit",
    "AI Library/20 Areas/Recurrent & Adaptive Computation/Universal Transformers",
    "AI Library/20 Areas/Recurrent & Adaptive Computation/Dynamic Depth",
    "AI Library/20 Areas/Efficient ML Systems/Efficient Architectures",
    "AI Library/20 Areas/Efficient ML Systems/Model Compression",
    "AI Library/20 Areas/Efficient ML Systems/Distillation",
    "AI Library/20 Areas/Efficient ML Systems/Parameter Sharing",
    "AI Library/20 Areas/Efficient ML Systems/Inference Acceleration",
    "AI Library/20 Areas/Efficient ML Systems/Edge Deployment",
    "AI Library/20 Areas/Computer Vision/CNN Architectures",
    "AI Library/20 Areas/Computer Vision/Vision Transformers",
    "AI Library/20 Areas/Computer Vision/State Space Vision Models",
    "AI Library/20 Areas/Computer Vision/Object Detection",
    "AI Library/20 Areas/Computer Vision/Segmentation",
    "AI Library/20 Areas/Computer Vision/Tracking & Correspondence",
    "AI Library/20 Areas/Computer Vision/Scene Flow & 3D Vision",
    "AI Library/20 Areas/Computer Vision/Image Classification",
    "AI Library/20 Areas/Computer Vision/Explainability & Attribution",
    "AI Library/20 Areas/Representation Learning/Self-Supervised Learning",
    "AI Library/20 Areas/Representation Learning/Contrastive Learning",
    "AI Library/20 Areas/Representation Learning/Semi-Supervised Learning",
    "AI Library/20 Areas/Representation Learning/Data Augmentation",
    "AI Library/20 Areas/Representation Learning/Transfer Learning",
    "AI Library/20 Areas/Representation Learning/Foundation Representations",
    "AI Library/20 Areas/Anomaly & Defect Detection/Industrial Anomaly Detection",
    "AI Library/20 Areas/Anomaly & Defect Detection/Visual Defect Inspection",
    "AI Library/20 Areas/Anomaly & Defect Detection/Zero-Shot Anomaly Detection",
    "AI Library/20 Areas/Anomaly & Defect Detection/Anomaly Segmentation",
    "AI Library/20 Areas/Anomaly & Defect Detection/Video Anomaly Detection",
    "AI Library/20 Areas/Anomaly & Defect Detection/Time-Series Anomaly Detection",
    "AI Library/20 Areas/Battery ML & Prognostics/Battery Life Prediction",
    "AI Library/20 Areas/Battery ML & Prognostics/RUL & SOH Estimation",
    "AI Library/20 Areas/Battery ML & Prognostics/Degradation Modeling",
    "AI Library/20 Areas/Battery ML & Prognostics/Fast Charging Optimization",
    "AI Library/20 Areas/Battery ML & Prognostics/Thermal Runaway & Safety",
    "AI Library/20 Areas/Battery ML & Prognostics/Battery Datasets",
    "AI Library/20 Areas/Battery ML & Prognostics/Physics-Informed Battery Models",
    "AI Library/20 Areas/Time-Series & Dynamical Systems/Neural ODEs & CDEs",
    "AI Library/20 Areas/Time-Series & Dynamical Systems/Model Predictive Control",
    "AI Library/20 Areas/Time-Series & Dynamical Systems/State-Space Models",
    "AI Library/20 Areas/Time-Series & Dynamical Systems/Dynamical Systems",
    "AI Library/20 Areas/Time-Series & Dynamical Systems/Wavelets & Signal Processing",
    "AI Library/20 Areas/Graph Learning/GNN Architectures",
    "AI Library/20 Areas/Graph Learning/Knowledge Graphs",
    "AI Library/20 Areas/Graph Learning/Graph Representation Learning",
    "AI Library/20 Areas/Graph Learning/Dynamic Graphs",
    "AI Library/20 Areas/Graph Learning/Graph Anomaly Detection",
    "AI Library/20 Areas/Medical AI/Biomedical VLMs",
    "AI Library/20 Areas/Medical AI/Radiology VLMs",
    "AI Library/20 Areas/Medical AI/Medical Representation Learning",
    "AI Library/20 Areas/Medical AI/Medical Segmentation",
    "AI Library/20 Areas/Medical AI/Medical Diagnosis",
    "AI Library/30 Resources/Foundational Papers",
    "AI Library/30 Resources/Surveys",
    "AI Library/30 Resources/Datasets",
    "AI Library/30 Resources/Benchmarks",
    "AI Library/30 Resources/Toolkits & Libraries",
    "AI Library/30 Resources/Open-Source Implementations",
    "AI Library/30 Resources/Evaluation Protocols",
    "AI Library/40 Cleanup/Duplicate Candidates",
    "AI Library/40 Cleanup/Missing Metadata",
    "AI Library/40 Cleanup/Missing Abstract",
    "AI Library/40 Cleanup/Broken PDF",
    "AI Library/40 Cleanup/Non-Paper Items",
    "AI Library/40 Cleanup/Low Confidence",
    "AI Library/90 Archives",
]

TAG_VOCABULARY_V3: list[str] = [
    "status/to-read",
    "status/skimmed",
    "status/read",
    "status/implemented",
    "status/cited",
    "status/review-needed",
    "area/llm",
    "area/vlm",
    "area/vla-robotics",
    "area/world-models",
    "area/recurrent-adaptive-computation",
    "area/efficient-ml",
    "area/classic-cv",
    "area/representation-learning",
    "area/anomaly-detection",
    "area/battery-ml",
    "area/time-series",
    "area/graph-learning",
    "area/medical-ai",
    "method/rag",
    "method/retrieval",
    "method/prompting",
    "method/cot",
    "method/latent-reasoning",
    "method/alignment",
    "method/jailbreak",
    "method/finetuning",
    "method/distillation",
    "method/kv-cache-compression",
    "method/world-model",
    "method/model-based-rl",
    "method/deferred-decoding",
    "method/looped-transformer",
    "method/recurrent-depth",
    "method/adaptive-computation",
    "method/early-exit",
    "method/parameter-sharing",
    "method/transformer",
    "method/cnn",
    "method/vit",
    "method/state-space-model",
    "method/mamba",
    "method/diffusion",
    "method/flow-matching",
    "method/control",
    "method/mpc",
    "method/neural-ode",
    "method/neural-cde",
    "method/gnn",
    "method/knowledge-graph",
    "method/contrastive-learning",
    "method/self-supervised-learning",
    "method/semi-supervised-learning",
    "method/data-augmentation",
    "method/prompt-learning",
    "method/adapter",
    "method/clip",
    "method/sam",
    "method/anomaly-localization",
    "method/physics-informed",
    "task/question-answering",
    "task/reasoning",
    "task/planning",
    "task/robot-manipulation",
    "task/imitation-learning",
    "task/action-prediction",
    "task/world-simulation",
    "task/video-prediction",
    "task/object-detection",
    "task/segmentation",
    "task/tracking",
    "task/scene-flow",
    "task/3d-reconstruction",
    "task/image-classification",
    "task/anomaly-detection",
    "task/defect-inspection",
    "task/battery-prognostics",
    "task/rul-prediction",
    "task/soh-estimation",
    "task/thermal-runaway",
    "task/medical-diagnosis",
    "task/multimodal-understanding",
    "type/method",
    "type/system",
    "type/dataset",
    "type/benchmark",
    "type/survey",
    "type/theory",
    "type/foundational",
    "type/tutorial",
    "type/non-paper",
    "source/arxiv",
    "source/conference",
    "source/journal",
    "source/workshop",
    "source/web",
    "source/local-pdf",
    "source/unknown",
    "cleanup/duplicate-candidate",
    "cleanup/missing-metadata",
    "cleanup/missing-abstract",
    "cleanup/broken-pdf",
    "cleanup/low-confidence",
    "cleanup/possible-existing",
    "cleanup/new-version",
    "paperflow/source-local-import",
]

TAG_SET_V3 = set(TAG_VOCABULARY_V3)
STATUS_TAGS_V3 = {tag for tag in TAG_SET_V3 if tag.startswith("status/")}
DEFAULT_STATUS_TAG_V3 = "status/to-read"


def normalize_title_v3(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower()
    value = re.sub(r"\b(arxiv|preprint|pdf)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output


def clamp_tags_v3(tags: Iterable[str], minimum: int = 5, maximum: int = 15) -> list[str]:
    cleaned = [tag for tag in unique_preserve_order(tags) if tag in TAG_SET_V3]
    status = (
        "status/review-needed"
        if "status/review-needed" in cleaned
        else next((tag for tag in cleaned if tag in STATUS_TAGS_V3), DEFAULT_STATUS_TAG_V3)
    )
    output = [status, *[tag for tag in cleaned if tag not in STATUS_TAGS_V3]]
    for fallback in ("type/method", "source/local-pdf", "source/unknown"):
        if len(output) >= minimum:
            break
        if fallback not in output:
            output.append(fallback)
    return output[:maximum]


def area_slug_from_collection(path: str | None) -> str:
    if not path or path == REVIEW_QUEUE_COLLECTION or "/05 Review Queue" in path:
        return "Review"
    parts = path.split("/")
    if len(parts) < 4:
        return "Review"
    slug = " - ".join(parts[2:])
    slug = re.sub(r"[^A-Za-z0-9 &+_.-]+", " ", slug)
    slug = re.sub(r"\s+", " ", slug).strip()
    return slug or "Review"
