from __future__ import annotations

from enum import StrEnum
from typing import Any

import httpx

from paperflow.models import OrganizePlan, PlannedAPICall
from paperflow.taxonomy import ROOT_COLLECTION


class ApplyMode(StrEnum):
    ADD_ONLY = "add-only"
    REPLACE_COLLECTIONS = "replace-collections"


class WebAPIBackendDisabled(RuntimeError):
    pass


class ZoteroWebClient:
    def __init__(
        self,
        user_id: str,
        api_key: str,
        base_url: str = "https://api.zotero.org",
        timeout: float = 30.0,
    ) -> None:
        self.user_id = user_id
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            timeout=timeout,
            headers={
                "Zotero-API-Key": api_key,
                "Zotero-API-Version": "3",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "ZoteroWebClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _url(self, path: str) -> str:
        return f"{self.base_url}/users/{self.user_id}/{path.lstrip('/')}"

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self.client.get(self._url(path), params=params)
        response.raise_for_status()
        return response.json()

    def iter_endpoint(self, path: str, limit: int = 100) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        start = 0
        while True:
            batch = self.get_json(
                path,
                params={"format": "json", "limit": limit, "start": start},
            )
            if not isinstance(batch, list):
                raise ValueError(f"Unexpected Zotero Web API response for {path}")
            rows.extend(batch)
            if len(batch) < limit:
                break
            start += len(batch)
        return rows

    def iter_items(self) -> list[dict[str, Any]]:
        return self.iter_endpoint("items")

    def iter_top_items(self) -> list[dict[str, Any]]:
        return self.iter_endpoint("items/top")

    def iter_collections(self) -> list[dict[str, Any]]:
        return self.iter_endpoint("collections")

    def iter_tags(self) -> list[dict[str, Any]]:
        return self.iter_endpoint("tags")

    def get_item_children(
        self, item_key: str, backend: str = "web"
    ) -> list[dict[str, Any]]:
        if backend != "web":
            raise ValueError("ZoteroWebClient only supports backend='web'")
        payload = self.get_json(
            f"items/{item_key}/children",
            params={"format": "json", "limit": 100},
        )
        return payload if isinstance(payload, list) else []

    def get_attachment_annotations(
        self, attachment_key: str, backend: str = "web"
    ) -> list[dict[str, Any]]:
        return [
            child
            for child in self.get_item_children(attachment_key, backend=backend)
            if child.get("data", {}).get("itemType") == "annotation"
        ]

    def patch_item(
        self,
        item_key: str,
        body: dict[str, Any],
        version: int | None = None,
    ) -> httpx.Response:
        headers = {}
        if version is not None:
            headers["If-Unmodified-Since-Version"] = str(version)
        response = self.client.patch(self._url(f"items/{item_key}"), json=body, headers=headers)
        if response.status_code == 412:
            latest = self.get_json(f"items/{item_key}", params={"format": "json"})
            latest_version = latest.get("version") or latest.get("data", {}).get("version")
            headers = {"If-Unmodified-Since-Version": str(latest_version)}
            response = self.client.patch(self._url(f"items/{item_key}"), json=body, headers=headers)
        response.raise_for_status()
        return response

    def post_collections(self, payload: list[dict[str, Any]]) -> httpx.Response:
        response = self.client.post(self._url("collections"), json=payload)
        response.raise_for_status()
        return response

    def post_items(self, payload: list[dict[str, Any]]) -> httpx.Response:
        response = self.client.post(self._url("items"), json=payload)
        response.raise_for_status()
        return response

    def patch_collection(
        self,
        collection_key: str,
        body: dict[str, Any],
        version: int | None = None,
    ) -> httpx.Response:
        headers = {}
        if version is not None:
            headers["If-Unmodified-Since-Version"] = str(version)
        response = self.client.patch(
            self._url(f"collections/{collection_key}"), json=body, headers=headers
        )
        if response.status_code == 412:
            latest = self.get_json(f"collections/{collection_key}", params={"format": "json"})
            latest_version = latest.get("version") or latest.get("data", {}).get("version")
            headers = {"If-Unmodified-Since-Version": str(latest_version)}
            response = self.client.patch(
                self._url(f"collections/{collection_key}"), json=body, headers=headers
            )
        response.raise_for_status()
        return response

    def delete_collection(self, collection_key: str, version: int | None = None) -> httpx.Response:
        headers = {}
        if version is not None:
            headers["If-Unmodified-Since-Version"] = str(version)
        response = self.client.delete(self._url(f"collections/{collection_key}"), headers=headers)
        if response.status_code == 412:
            latest = self.get_json(f"collections/{collection_key}", params={"format": "json"})
            latest_version = latest.get("version") or latest.get("data", {}).get("version")
            headers = {"If-Unmodified-Since-Version": str(latest_version)}
            response = self.client.delete(
                self._url(f"collections/{collection_key}"), headers=headers
            )
        response.raise_for_status()
        return response

    def delete_item(self, item_key: str, version: int | None = None) -> httpx.Response:
        headers = {}
        if version is not None:
            headers["If-Unmodified-Since-Version"] = str(version)
        response = self.client.delete(self._url(f"items/{item_key}"), headers=headers)
        if response.status_code == 412:
            latest = self.get_json(f"items/{item_key}", params={"format": "json"})
            latest_version = latest.get("version") or latest.get("data", {}).get("version")
            headers = {"If-Unmodified-Since-Version": str(latest_version)}
            response = self.client.delete(self._url(f"items/{item_key}"), headers=headers)
        response.raise_for_status()
        return response


def build_planned_api_calls(
    plan: OrganizePlan,
    user_id: str,
    mode: ApplyMode,
    base_url: str = "https://api.zotero.org",
) -> list[PlannedAPICall]:
    prefix = f"{base_url.rstrip('/')}/users/{user_id}"
    calls: list[PlannedAPICall] = [
        PlannedAPICall(
            method="GET",
            url=f"{prefix}/collections?format=json",
            note="Read existing collections before creating the AI Library tree.",
        ),
        PlannedAPICall(
            method="POST",
            url=f"{prefix}/collections",
            body={
                "collections": [
                    {"name": ROOT_COLLECTION, "parentCollection": False},
                    *[
                        {
                            "path": collection,
                            "parentCollection": "resolved-parent-key",
                        }
                        for collection in plan.collection_tree
                    ],
                ]
            },
            note="Create missing AI Library collections only.",
        ),
    ]

    for item in plan.items:
        if mode == ApplyMode.ADD_ONLY:
            body = {
                "tags": [{"tag": tag} for tag in item.normalized_tags],
                "collections": {
                    "operation": "merge",
                    "plannedCollectionPaths": item.target_collections,
                },
            }
            note = "Merge planned tags and collections; preserve existing memberships."
        else:
            body = {
                "tags": [{"tag": tag} for tag in item.normalized_tags],
                "collections": {
                    "operation": "replace",
                    "plannedCollectionPaths": item.target_collections,
                },
            }
            note = "Replace item collection memberships with planned memberships."

        calls.append(
            PlannedAPICall(
                method="PATCH",
                url=f"{prefix}/items/{item.item_key}",
                body=body,
                note=note,
            )
        )
    return calls


def apply_plan_with_web_api(*_: object, **__: object) -> None:
    raise WebAPIBackendDisabled(
        "Zotero Web API write backend is not implemented in this version. "
        "No Zotero writes were executed."
    )
