from __future__ import annotations

import re
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from paperflow.models import Attachment, Creator, ZoteroItem
from paperflow.reading_activity import collect_reading_activity_from_children
from paperflow.zotero_web import ZoteroWebClient


DEFAULT_LOCAL_API_BASE_URL = "http://localhost:23119/api/"
DEFAULT_LIBRARY_PREFIX = "/users/0"


class LocalAPIUnavailable(RuntimeError):
    pass


LOCAL_API_SETUP_MESSAGE = (
    "Zotero Local API is not reachable. Start Zotero Desktop and enable local "
    "API access in Zotero settings/preferences under Advanced. The expected "
    f"base URL is {DEFAULT_LOCAL_API_BASE_URL}."
)


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def extract_year(date_value: str | None) -> int | None:
    if not date_value:
        return None
    match = re.search(r"\b(16|17|18|19|20|21)\d{2}\b", date_value)
    return int(match.group(0)) if match else None


def is_regular_parent_item(raw_item: dict[str, Any]) -> bool:
    data = raw_item.get("data", {})
    item_type = data.get("itemType")
    if item_type in {"note", "attachment"}:
        return False
    if data.get("deleted") or raw_item.get("deleted"):
        return False
    return bool(raw_item.get("key") or data.get("key"))


def parse_creator(raw_creator: dict[str, Any]) -> Creator:
    return Creator(
        creator_type=_clean_optional(raw_creator.get("creatorType")),
        first_name=_clean_optional(raw_creator.get("firstName")),
        last_name=_clean_optional(raw_creator.get("lastName")),
        name=_clean_optional(raw_creator.get("name")),
    )


def parse_attachment(raw_attachment: dict[str, Any], local_path: str | None = None) -> Attachment:
    data = raw_attachment.get("data", {})
    path = local_path or _local_path_from_attachment_data(data)
    return Attachment(
        key=str(raw_attachment.get("key") or data.get("key")),
        title=_clean_optional(data.get("title")),
        content_type=_clean_optional(data.get("contentType")),
        filename=_clean_optional(data.get("filename")),
        local_path=path,
    )


def _local_path_from_attachment_data(data: dict[str, Any]) -> str | None:
    path = _clean_optional(data.get("path"))
    if path and not path.startswith("storage:") and Path(path).is_absolute():
        return path
    return None


def parse_zotero_item(
    raw_item: dict[str, Any],
    child_attachments: list[Attachment] | None = None,
    reading_activity: Any | None = None,
) -> ZoteroItem:
    data = raw_item.get("data", {})
    date_value = _clean_optional(data.get("date"))
    attachments = child_attachments or []
    payload = {
        "key": str(raw_item.get("key") or data.get("key")),
        "version": raw_item.get("version") or data.get("version"),
        "item_type": str(data.get("itemType") or ""),
        "title": _clean_optional(data.get("title")),
        "creators": [parse_creator(creator) for creator in data.get("creators", [])],
        "date": date_value,
        "date_modified": _clean_optional(data.get("dateModified") or raw_item.get("dateModified")),
        "year": extract_year(date_value),
        "doi": _clean_optional(data.get("DOI") or data.get("doi")),
        "url": _clean_optional(data.get("url")),
        "abstract_note": _clean_optional(data.get("abstractNote")),
        "extra": _clean_optional(data.get("extra")),
        "publication_title": _clean_optional(
            data.get("publicationTitle")
            or data.get("proceedingsTitle")
            or data.get("conferenceName")
            or data.get("websiteTitle")
        ),
        "existing_tags": [
            tag.get("tag", "").strip()
            for tag in data.get("tags", [])
            if tag.get("tag", "").strip()
        ],
        "existing_collection_keys": list(data.get("collections", [])),
        "child_attachment_keys": [attachment.key for attachment in attachments],
        "attachments": attachments,
    }
    if reading_activity:
        payload["note_count"] = reading_activity.note_count
        payload["annotation_count"] = reading_activity.annotation_count
        payload["reading_activity"] = reading_activity
    return ZoteroItem(**payload)


def extract_local_file_path_from_response(response: httpx.Response) -> str | None:
    location = response.headers.get("location") or response.headers.get("Location")
    if location:
        parsed = urlparse(location)
        if parsed.scheme == "file":
            return unquote(parsed.path)
        if Path(location).is_absolute():
            return location

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = response.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            for key in ("path", "localPath", "filePath"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value.removeprefix("file://")

    text = ""
    try:
        text = response.text[:2000]
    except Exception:
        return None

    file_match = re.search(r"file://([^\s\"']+)", text)
    if file_match:
        return unquote(urlparse("file://" + file_match.group(1)).path)

    absolute_match = re.search(r"(/[^\"'\n\r\t]+\.pdf)\b", text)
    if absolute_match:
        return unquote(absolute_match.group(1))
    return None


class ZoteroLocalClient:
    def __init__(
        self,
        base_url: str = DEFAULT_LOCAL_API_BASE_URL,
        library_prefix: str = DEFAULT_LIBRARY_PREFIX,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.library_prefix = "/" + library_prefix.strip("/")
        self.client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> ZoteroLocalClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{self.library_prefix}/{path.lstrip('/')}"

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = self.client.get(self._url(path), params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            raise LocalAPIUnavailable(LOCAL_API_SETUP_MESSAGE) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in {403, 404, 409, 500, 503}:
                raise LocalAPIUnavailable(LOCAL_API_SETUP_MESSAGE) from exc
            raise

    def health_check(self) -> bool:
        """Check Local API availability with one bounded read-only request."""

        payload = self._get_json("items/top", params={"format": "json", "limit": 1})
        if not isinstance(payload, list):
            raise ValueError("Unexpected Zotero Local API health response")
        return True

    def iter_top_items(self, limit: int = 100) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        start = 0
        while True:
            batch = self._get_json(
                "items/top",
                params={"format": "json", "limit": limit, "start": start},
            )
            if not isinstance(batch, list):
                raise ValueError("Unexpected Zotero Local API response for items/top")
            items.extend(batch)
            if len(batch) < limit:
                break
            start += len(batch)
        return items

    def iter_items(self, limit: int = 100) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        start = 0
        while True:
            batch = self._get_json(
                "items",
                params={"format": "json", "limit": limit, "start": start},
            )
            if not isinstance(batch, list):
                raise ValueError("Unexpected Zotero Local API response for items")
            items.extend(batch)
            if len(batch) < limit:
                break
            start += len(batch)
        return items

    def iter_collections(self, limit: int = 100) -> list[dict[str, Any]]:
        collections: list[dict[str, Any]] = []
        start = 0
        while True:
            batch = self._get_json(
                "collections",
                params={"format": "json", "limit": limit, "start": start},
            )
            if not isinstance(batch, list):
                raise ValueError("Unexpected Zotero Local API response for collections")
            collections.extend(batch)
            if len(batch) < limit:
                break
            start += len(batch)
        return collections

    def iter_tags(self, limit: int = 100) -> list[dict[str, Any]]:
        tags: list[dict[str, Any]] = []
        start = 0
        while True:
            batch = self._get_json(
                "tags",
                params={"format": "json", "limit": limit, "start": start},
            )
            if not isinstance(batch, list):
                raise ValueError("Unexpected Zotero Local API response for tags")
            tags.extend(batch)
            if len(batch) < limit:
                break
            start += len(batch)
        return tags

    def get_children(self, item_key: str) -> list[dict[str, Any]]:
        payload = self._get_json(
            f"items/{item_key}/children",
            params={"format": "json", "limit": 100},
        )
        if not isinstance(payload, list):
            return []
        return payload

    def get_item_children(self, item_key: str, backend: str = "local") -> list[dict[str, Any]]:
        if backend != "local":
            raise ValueError("ZoteroLocalClient only supports backend='local'")
        return self.get_children(item_key)

    def get_attachment_annotations(
        self, attachment_key: str, backend: str = "local"
    ) -> list[dict[str, Any]]:
        if backend != "local":
            raise ValueError("ZoteroLocalClient only supports backend='local'")
        return [
            child
            for child in self.get_children(attachment_key)
            if child.get("data", {}).get("itemType") == "annotation"
        ]

    def _web_client_from_env(self) -> ZoteroWebClient | None:
        user_id = os.environ.get("ZOTERO_USER_ID")
        api_key = os.environ.get("ZOTERO_API_KEY")
        if not user_id or not api_key:
            return None
        return ZoteroWebClient(user_id=user_id, api_key=api_key)

    def collect_parent_reading_activity(
        self,
        raw_children: list[dict[str, Any]],
        web_client: ZoteroWebClient | None = None,
    ):
        attachment_annotations: dict[str, list[dict[str, Any]]] = {}
        for child in raw_children:
            data = child.get("data", {})
            if data.get("itemType") != "attachment":
                continue
            attachment = parse_attachment(child)
            if not attachment.is_pdf:
                continue
            try:
                annotations = self.get_attachment_annotations(attachment.key)
            except Exception:
                annotations = []
            if not annotations and web_client is not None:
                try:
                    annotations = web_client.get_attachment_annotations(attachment.key)
                except Exception:
                    annotations = []
            attachment_annotations[attachment.key] = annotations
        return collect_reading_activity_from_children(raw_children, attachment_annotations)

    def resolve_attachment_file_path(self, attachment_key: str) -> str | None:
        url = self._url(f"items/{attachment_key}/file")
        for method in ("HEAD", "GET"):
            try:
                if method == "GET":
                    with self.client.stream(
                        method, url, follow_redirects=False
                    ) as response:
                        return extract_local_file_path_from_response(response)
                response = self.client.request(method, url, follow_redirects=False)
                path = extract_local_file_path_from_response(response)
                if path:
                    return path
                if response.status_code not in {405, 404}:
                    return None
            except (httpx.HTTPError, RuntimeError):
                return None
        return None

    def scan_items(self) -> list[ZoteroItem]:
        scanned: list[ZoteroItem] = []
        web_client = self._web_client_from_env()
        try:
            for raw_item in self.iter_top_items():
                if not is_regular_parent_item(raw_item):
                    continue
                raw_children = self.get_item_children(
                    str(raw_item.get("key") or raw_item["data"]["key"])
                )
                attachments: list[Attachment] = []
                for child in raw_children:
                    child_data = child.get("data", {})
                    if child_data.get("itemType") != "attachment":
                        continue
                    attachment = parse_attachment(child)
                    if attachment.is_pdf and not attachment.local_path:
                        attachment.local_path = self.resolve_attachment_file_path(attachment.key)
                    attachments.append(attachment)
                reading_activity = self.collect_parent_reading_activity(
                    raw_children,
                    web_client=web_client,
                )
                scanned.append(parse_zotero_item(raw_item, attachments, reading_activity))
        finally:
            if web_client is not None:
                web_client.close()
        return scanned
