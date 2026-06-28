from paperflow.dedupe import build_dedupe_plan
from paperflow.metadata import enrich_item
from paperflow.migration_models import DedupePlan
from paperflow.models import Attachment, Creator, ReadingActivity, ZoteroItem


def _item(
    key: str,
    title: str = "Duplicate Paper",
    doi: str | None = "10.1234/duplicate",
    url: str | None = None,
    abstract: str | None = "Abstract.",
    year: int | None = 2024,
    arxiv_url: str | None = None,
    reading: ReadingActivity | None = None,
    pdf: bool = False,
    creators: int = 1,
) -> object:
    item = ZoteroItem(
        key=key,
        item_type="journalArticle",
        title=title,
        abstract_note=abstract,
        doi=doi,
        url=arxiv_url or url,
        year=year,
        publication_title="ICLR" if abstract else None,
        creators=[
            Creator(first_name=f"Author{idx}", last_name="Example")
            for idx in range(creators)
        ],
        attachments=[
            Attachment(key=f"{key}PDF", filename="paper.pdf", content_type="application/pdf")
        ]
        if pdf
        else [],
        reading_activity=reading or ReadingActivity(),
        version=1,
    )
    return enrich_item(item)


def _canonical_key(*items) -> str:
    plan = build_dedupe_plan(list(items), source_jsonl="test.jsonl")
    return plan.groups[0].canonical_item_key


def _group(*items):
    return build_dedupe_plan(list(items), source_jsonl="test.jsonl").groups[0]


def test_duplicate_detection_by_doi() -> None:
    group = _group(
        _item("A", doi="10.1234/ABC"),
        _item("B", doi="https://doi.org/10.1234/abc"),
    )

    assert group.match_type == "strong_doi"


def test_duplicate_detection_by_arxiv_id() -> None:
    group = _group(
        _item("A", doi=None, arxiv_url="https://arxiv.org/abs/2401.12345"),
        _item("B", doi="10.48550/arXiv.2401.12345"),
    )

    assert group.match_type == "strong_arxiv"


def test_duplicate_detection_by_normalized_title() -> None:
    group = _group(
        _item("A", "A Study of Vision Language Models", doi=None),
        _item("B", "A Study of Vision-Language Models", doi=None),
    )

    assert group.match_type == "likely_title"


def test_canonical_prefers_child_note_over_better_metadata() -> None:
    canonical = _item(
        "NOTE",
        abstract=None,
        reading=ReadingActivity(note_count=1, note_char_count=300),
    )
    better_metadata = _item("META", url="https://example.org", pdf=True, creators=5)

    assert _canonical_key(canonical, better_metadata) == "NOTE"


def test_canonical_prefers_highlights_over_better_metadata() -> None:
    canonical = _item(
        "HIGH",
        abstract=None,
        reading=ReadingActivity(annotation_count=4, highlight_count=4),
    )
    better_metadata = _item("META", url="https://example.org", pdf=True, creators=5)

    assert _canonical_key(canonical, better_metadata) == "HIGH"


def test_canonical_prefers_underlines_over_better_metadata() -> None:
    canonical = _item(
        "UNDER",
        abstract=None,
        reading=ReadingActivity(annotation_count=3, underline_count=3),
    )
    better_metadata = _item("META", url="https://example.org", pdf=True, creators=5)

    assert _canonical_key(canonical, better_metadata) == "UNDER"


def test_canonical_prefers_annotation_comments_over_better_metadata() -> None:
    canonical = _item(
        "COMM",
        abstract=None,
        reading=ReadingActivity(annotation_count=1, comment_count=1),
    )
    better_metadata = _item("META", url="https://example.org", pdf=True, creators=5)

    assert _canonical_key(canonical, better_metadata) == "COMM"


def test_if_both_have_reading_work_canonical_prefers_more_reading_work() -> None:
    little = _item("LITTLE", reading=ReadingActivity(highlight_count=1, annotation_count=1))
    more = _item("MORE", reading=ReadingActivity(highlight_count=4, annotation_count=4))

    assert _canonical_key(little, more) == "MORE"


def test_if_neither_has_reading_work_canonical_prefers_pdf_attachment() -> None:
    no_pdf = _item("NOPDF", pdf=False)
    with_pdf = _item("PDF", pdf=True)

    assert _canonical_key(no_pdf, with_pdf) == "PDF"


def test_if_neither_has_reading_and_both_pdf_canonical_prefers_metadata() -> None:
    weak = _item("WEAK", abstract=None, pdf=True, creators=0)
    strong = _item("STRONG", url="https://example.org", pdf=True, creators=5)

    assert _canonical_key(weak, strong) == "STRONG"


def test_non_canonical_duplicate_with_reading_work_is_unsafe_to_delete() -> None:
    less_reading = _item("LESS", reading=ReadingActivity(highlight_count=1, annotation_count=1))
    more_reading = _item("MORE", reading=ReadingActivity(highlight_count=4, annotation_count=4))

    group = _group(less_reading, more_reading)
    less = next(item for item in group.items if item.item_key == "LESS")

    assert group.canonical_item_key == "MORE"
    assert less.unsafe_to_delete is True


def test_metadata_merge_suggested_when_canonical_has_reading_but_weaker_metadata() -> None:
    reading_item = _item(
        "READ",
        abstract=None,
        creators=0,
        reading=ReadingActivity(note_count=1, note_char_count=200),
    )
    metadata_item = _item("META", url="https://example.org", pdf=True, creators=5)

    group = _group(reading_item, metadata_item)

    assert group.canonical_item_key == "READ"
    assert group.metadata_merge_suggested is True
    assert group.suggested_metadata_source_item_key == "META"


def test_dedupe_plan_json_validates_against_schema() -> None:
    plan = build_dedupe_plan(
        [_item("A", pdf=True), _item("B", reading=ReadingActivity(note_count=1))],
        source_jsonl="test.jsonl",
    )

    validated = DedupePlan.model_validate_json(plan.model_dump_json())

    assert validated.schema_version == "2.0"
    assert validated.groups[0].canonical_item_key == "B"
