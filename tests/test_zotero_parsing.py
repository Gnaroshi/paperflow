import httpx

from paperflow.zotero_local import (
    extract_local_file_path_from_response,
    is_regular_parent_item,
    parse_attachment,
    parse_zotero_item,
)


def test_zotero_local_api_response_parsing() -> None:
    raw_item = {
        "key": "ITEM123",
        "version": 42,
        "data": {
            "key": "ITEM123",
            "itemType": "conferencePaper",
            "title": "A Benchmark for Code Generation",
            "creators": [
                {
                    "creatorType": "author",
                    "firstName": "Ada",
                    "lastName": "Lovelace",
                }
            ],
            "date": "2024-05-01",
            "DOI": "10.1234/example",
            "url": "https://example.org/paper",
            "abstractNote": "A benchmark paper.",
            "publicationTitle": "ICLR",
            "tags": [{"tag": "Benchmark"}],
            "collections": ["OLDCOLL"],
        },
    }
    raw_attachment = {
        "key": "ATT123",
        "data": {
            "key": "ATT123",
            "itemType": "attachment",
            "title": "Full Text PDF",
            "contentType": "application/pdf",
            "filename": "paper.pdf",
        },
    }

    attachment = parse_attachment(raw_attachment, "/Users/me/Zotero/storage/ATT123/paper.pdf")
    item = parse_zotero_item(raw_item, [attachment])

    assert is_regular_parent_item(raw_item)
    assert item.key == "ITEM123"
    assert item.version == 42
    assert item.year == 2024
    assert item.creators[0].last_name == "Lovelace"
    assert item.existing_tags == ["Benchmark"]
    assert item.existing_collection_keys == ["OLDCOLL"]
    assert item.child_attachment_keys == ["ATT123"]
    assert item.attachments[0].is_pdf


def test_zotero_excludes_notes_attachments_and_trash() -> None:
    assert not is_regular_parent_item({"key": "N", "data": {"itemType": "note"}})
    assert not is_regular_parent_item({"key": "A", "data": {"itemType": "attachment"}})
    assert not is_regular_parent_item(
        {"key": "T", "data": {"itemType": "journalArticle", "deleted": True}}
    )


def test_extract_local_file_path_from_file_endpoint_redirect() -> None:
    response = httpx.Response(
        302,
        headers={"Location": "file:///Users/me/Zotero/storage/ATT123/paper.pdf"},
    )

    assert (
        extract_local_file_path_from_response(response)
        == "/Users/me/Zotero/storage/ATT123/paper.pdf"
    )
