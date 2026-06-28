from __future__ import annotations

import re
from html import unescape
from typing import Any

from paperflow.models import Attachment, ReadingActivity


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else plural or singular + 's'}"


def reading_activity_score(activity: ReadingActivity) -> float:
    return round(
        activity.note_count * 100
        + activity.note_char_count * 0.02
        + activity.annotation_count * 20
        + activity.highlight_count * 30
        + activity.underline_count * 25
        + activity.comment_count * 40
        + activity.annotation_text_char_count * 0.01,
        2,
    )


def finalize_reading_activity(activity: ReadingActivity) -> ReadingActivity:
    evidence: list[str] = []
    if activity.note_count:
        evidence.append(_plural(activity.note_count, "child note"))
    if activity.annotation_count:
        evidence.append(_plural(activity.annotation_count, "PDF annotation"))
    if activity.highlight_count:
        evidence.append(_plural(activity.highlight_count, "highlight"))
    if activity.underline_count:
        evidence.append(_plural(activity.underline_count, "underline"))
    if activity.comment_count:
        evidence.append(_plural(activity.comment_count, "annotation comment"))
    if activity.note_char_count:
        evidence.append(f"{activity.note_char_count} note characters")
    if activity.annotation_text_char_count:
        evidence.append(f"{activity.annotation_text_char_count} annotation text characters")

    activity.has_reading_work = bool(
        activity.note_count
        or activity.annotation_count
        or activity.highlight_count
        or activity.underline_count
        or activity.comment_count
        or activity.note_char_count
        or activity.annotation_text_char_count
    )
    activity.score = reading_activity_score(activity)
    activity.evidence = evidence
    return activity


def annotation_activity(raw_annotation: dict[str, Any]) -> ReadingActivity:
    data = raw_annotation.get("data", raw_annotation)
    activity = ReadingActivity(annotation_count=1)
    annotation_type = _clean_text(data.get("annotationType")).lower()
    annotation_text = _clean_text(data.get("annotationText"))
    annotation_comment = _clean_text(data.get("annotationComment"))
    if annotation_type == "highlight":
        activity.highlight_count = 1
    if annotation_type == "underline":
        activity.underline_count = 1
    if annotation_comment:
        activity.comment_count = 1
    if annotation_text:
        activity.annotation_text_char_count = len(annotation_text)
    return activity


def add_activity(target: ReadingActivity, source: ReadingActivity) -> ReadingActivity:
    target.note_count += source.note_count
    target.note_char_count += source.note_char_count
    target.attachment_count += source.attachment_count
    target.pdf_attachment_count += source.pdf_attachment_count
    target.annotation_count += source.annotation_count
    target.highlight_count += source.highlight_count
    target.underline_count += source.underline_count
    target.comment_count += source.comment_count
    target.annotation_text_char_count += source.annotation_text_char_count
    return target


def collect_reading_activity_from_children(
    child_items: list[dict[str, Any]],
    attachment_annotations: dict[str, list[dict[str, Any]]] | None = None,
) -> ReadingActivity:
    attachment_annotations = attachment_annotations or {}
    activity = ReadingActivity()
    for child in child_items:
        data = child.get("data", child)
        item_type = data.get("itemType")
        if item_type == "note":
            note_text = _clean_text(data.get("note"))
            activity.note_count += 1
            activity.note_char_count += len(note_text)
            continue
        if item_type != "attachment":
            continue

        activity.attachment_count += 1
        attachment = Attachment(
            key=str(child.get("key") or data.get("key")),
            title=data.get("title"),
            content_type=data.get("contentType"),
            filename=data.get("filename"),
            local_path=data.get("path"),
        )
        if not attachment.is_pdf:
            continue
        activity.pdf_attachment_count += 1
        for annotation in attachment_annotations.get(attachment.key, []):
            annotation_data = annotation.get("data", annotation)
            if annotation_data.get("itemType") == "annotation":
                add_activity(activity, annotation_activity(annotation))
    return finalize_reading_activity(activity)


def merge_reading_activity(
    base: ReadingActivity,
    extra: ReadingActivity,
) -> ReadingActivity:
    add_activity(base, extra)
    return finalize_reading_activity(base)
