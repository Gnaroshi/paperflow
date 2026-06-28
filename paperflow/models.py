from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from paperflow.taxonomy import COLLECTION_TREE, STATUS_TAGS, TAG_SET


class Creator(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    creator_type: str | None = Field(default=None, alias="creatorType")
    first_name: str | None = Field(default=None, alias="firstName")
    last_name: str | None = Field(default=None, alias="lastName")
    name: str | None = None


class Attachment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str
    title: str | None = None
    content_type: str | None = Field(default=None, alias="contentType")
    filename: str | None = None
    local_path: str | None = Field(default=None, alias="localPath")

    @property
    def is_pdf(self) -> bool:
        content_type = (self.content_type or "").lower()
        filename = (self.filename or self.local_path or "").lower()
        return content_type == "application/pdf" or filename.endswith(".pdf")


class ReadingActivity(BaseModel):
    note_count: int = 0
    note_char_count: int = 0
    attachment_count: int = 0
    pdf_attachment_count: int = 0
    annotation_count: int = 0
    highlight_count: int = 0
    underline_count: int = 0
    comment_count: int = 0
    annotation_text_char_count: int = 0
    has_reading_work: bool = False
    score: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class ZoteroItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str
    version: int | None = None
    item_type: str = Field(alias="itemType")
    title: str | None = None
    creators: list[Creator] = Field(default_factory=list)
    date: str | None = None
    date_modified: str | None = Field(default=None, alias="dateModified")
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    abstract_note: str | None = Field(default=None, alias="abstractNote")
    publication_title: str | None = Field(default=None, alias="publicationTitle")
    extra: str | None = Field(default=None, alias="extra")
    existing_tags: list[str] = Field(default_factory=list, alias="existingTags")
    existing_collection_keys: list[str] = Field(
        default_factory=list, alias="existingCollectionKeys"
    )
    child_attachment_keys: list[str] = Field(
        default_factory=list, alias="childAttachmentKeys"
    )
    attachments: list[Attachment] = Field(default_factory=list)
    note_count: int = Field(default=0, alias="noteCount")
    annotation_count: int = Field(default=0, alias="annotationCount")
    reading_activity: ReadingActivity = Field(default_factory=ReadingActivity)


class PlanItem(BaseModel):
    item_key: str
    version: int | None = None
    title: str | None = None
    doi: str | None = None
    url: str | None = None
    year: int | None = None
    abstract_present: bool = False
    publication_title: str | None = None
    target_collections: list[str]
    normalized_tags: list[str]
    confidence: float = Field(ge=0, le=1)
    rationale: str

    @field_validator("target_collections")
    @classmethod
    def validate_collections(cls, value: list[str]) -> list[str]:
        if not 1 <= len(value) <= 3:
            raise ValueError("each item must have 1 to 3 target collections")
        invalid = [collection for collection in value if collection not in COLLECTION_TREE]
        if invalid:
            raise ValueError(f"unknown target collections: {invalid}")
        return value

    @field_validator("normalized_tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        if not 3 <= len(value) <= 10:
            raise ValueError("each item must have 3 to 10 normalized tags")
        invalid = [tag for tag in value if tag not in TAG_SET]
        if invalid:
            raise ValueError(f"unknown normalized tags: {invalid}")
        status_count = sum(1 for tag in value if tag in STATUS_TAGS)
        if status_count != 1:
            raise ValueError("each item must have exactly one status tag")
        return value


class PlanStats(BaseModel):
    scanned_items: int
    classified_items: int
    inbox_items: int
    low_confidence_items: int


class OrganizePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_jsonl: str
    collection_tree: list[str] = Field(default_factory=lambda: list(COLLECTION_TREE))
    tag_vocabulary: list[str]
    stats: PlanStats
    items: list[PlanItem]


class PlannedAPICall(BaseModel):
    method: str
    url: str
    body: dict[str, Any] | None = None
    note: str | None = None


def json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
