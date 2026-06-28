from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from paperflow.models import ReadingActivity, ZoteroItem
from paperflow.taxonomy_v2 import COLLECTION_TREE_V2, STATUS_TAGS_V2, TAG_SET_V2


class EnrichedZoteroItem(ZoteroItem):
    normalized_title: str = ""
    arxiv_id: str | None = None
    doi_normalized: str | None = None
    metadata_quality_score: float = Field(default=0.0, ge=0, le=1)
    metadata_issues: list[str] = Field(default_factory=list)


DuplicateRole = Literal["canonical", "duplicate_candidate"]
DuplicateMatchType = Literal[
    "strong_doi",
    "strong_arxiv",
    "likely_title",
    "possible_fuzzy_title",
]


class DuplicateItem(BaseModel):
    item_key: str
    title: str | None = None
    doi_normalized: str | None = None
    arxiv_id: str | None = None
    year: int | None = None
    has_pdf_attachment: bool = False
    metadata_quality_score: int = Field(ge=0, le=100)
    reading_activity: ReadingActivity = Field(default_factory=ReadingActivity)
    canonical_rank_tuple: list[Any]
    is_canonical: bool = False
    unsafe_to_delete: bool = False


class DuplicateGroup(BaseModel):
    group_id: str
    match_type: DuplicateMatchType
    normalized_title: str
    canonical_item_key: str
    canonical_reason: str
    metadata_merge_suggested: bool = False
    suggested_metadata_source_item_key: str | None = None
    items: list[DuplicateItem]
    recommended_action: str = "keep_canonical_tag_others_review_metadata_merge"


class DedupePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "2.0"
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_jsonl: str
    groups: list[DuplicateGroup] = Field(default_factory=list)

    @property
    def duplicate_candidate_keys(self) -> set[str]:
        return {
            item.item_key
            for group in self.groups
            for item in group.items
            if not item.is_canonical
        }


class MigrationItem(BaseModel):
    item_key: str
    version: int | None = None
    title: str | None = None
    normalized_title: str = ""
    item_type: str
    year: int | None = None
    doi: str | None = None
    doi_normalized: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    abstract_present: bool = False
    publication_title: str | None = None
    existing_collection_keys: list[str] = Field(default_factory=list)
    existing_tags: list[str] = Field(default_factory=list)
    target_collections: list[str]
    normalized_tags: list[str]
    duplicate_role: DuplicateRole | None = None
    canonical_item_key: str | None = None
    metadata_quality_score: float = Field(ge=0, le=1)
    metadata_issues: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    rationale: str

    @field_validator("target_collections")
    @classmethod
    def validate_collections(cls, value: list[str]) -> list[str]:
        if not 1 <= len(value) <= 3:
            raise ValueError("each item must have 1 to 3 target collections")
        invalid = [collection for collection in value if collection not in COLLECTION_TREE_V2]
        if invalid:
            raise ValueError(f"unknown target collections: {invalid}")
        return value

    @field_validator("normalized_tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        if not 3 <= len(value) <= 10:
            raise ValueError("each item must have 3 to 10 normalized tags")
        invalid = [tag for tag in value if tag not in TAG_SET_V2]
        if invalid:
            raise ValueError(f"unknown normalized tags: {invalid}")
        status_count = sum(1 for tag in value if tag in STATUS_TAGS_V2)
        if status_count != 1:
            raise ValueError("each item must have exactly one status tag")
        return value


class MigrationStats(BaseModel):
    source_items: int
    planned_items: int
    duplicate_candidates: int
    missing_metadata: int
    missing_abstract: int
    non_paper_items: int


class MigrationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "2.0"
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_jsonl: str
    dedupe_plan: str | None = None
    collection_tree: list[str] = Field(default_factory=lambda: list(COLLECTION_TREE_V2))
    tag_vocabulary: list[str]
    stats: MigrationStats
    items: list[MigrationItem]


class BackupManifest(BaseModel):
    schema_version: str = "1.0"
    generated_at: str
    item_count: int
    collection_count: int
    tag_count: int
    membership_count: int
    source: Literal["local-api", "web-api"]


class ApplyOperation(BaseModel):
    method: str
    url: str
    body: dict[str, Any] | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    note: str | None = None


class ApplyPreview(BaseModel):
    schema_version: str = "1.0"
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    collection_mode: str
    tag_mode: str
    collections_to_create: list[dict[str, Any]] = Field(default_factory=list)
    item_updates: list[dict[str, Any]] = Field(default_factory=list)
    old_collections_that_would_be_empty: list[dict[str, Any]] = Field(default_factory=list)
    operations: list[ApplyOperation] = Field(default_factory=list)


class CleanupReport(BaseModel):
    schema_version: str = "1.0"
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    mode: str
    collections: list[dict[str, Any]]
    operations: list[ApplyOperation] = Field(default_factory=list)


class RollbackPlan(BaseModel):
    schema_version: str = "1.0"
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    backup_dir: str
    recreate_collections: list[dict[str, Any]] = Field(default_factory=list)
    item_updates: list[dict[str, Any]] = Field(default_factory=list)
    remove_new_collections: bool = False
