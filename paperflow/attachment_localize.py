from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from paperflow.ingest import _created_key, linked_attachment_body, sha256_file
from paperflow.metadata import enrich_item
from paperflow.models import ReadingActivity
from paperflow.reading_activity import (
    add_activity,
    annotation_activity,
    finalize_reading_activity,
)
from paperflow.utils import dump_json_data, ensure_parent_dir
from paperflow.vault import DEFAULT_VAULT_LIBRARY, dedupe_target_path, target_path_for_item
from paperflow.vault import zotero_linked_attachment_path
from paperflow.zotero_local import (
    DEFAULT_LIBRARY_PREFIX,
    DEFAULT_LOCAL_API_BASE_URL,
    LOCAL_API_SETUP_MESSAGE,
    LocalAPIUnavailable,
    ZoteroLocalClient,
    parse_attachment,
    parse_zotero_item,
)
from paperflow.zotero_web import ZoteroWebClient


LOCALIZE_CONFIRMATION = "LOCALIZE ZOTERO PDF ATTACHMENTS"
CLEANUP_STORED_CONFIRMATION = "DELETE OLD STORED PDF ATTACHMENTS"
BRIDGE_NOTE = (
    "This uses Zotero item records with linkMode=linked_file and never calls "
    "Zotero file upload APIs. If a Zotero installation rejects linked local file "
    "records through the Web API, this workflow requires a Zotero Desktop local bridge."
)


def _key(raw_item: dict[str, Any]) -> str:
    data = raw_item.get("data", {})
    return str(raw_item.get("key") or data.get("key"))


def _version(raw_item: dict[str, Any]) -> int | None:
    data = raw_item.get("data", {})
    value = raw_item.get("version") or data.get("version")
    return int(value) if value is not None else None


def is_stored_pdf_attachment(raw_attachment: dict[str, Any]) -> bool:
    data = raw_attachment.get("data", {})
    if data.get("itemType") != "attachment":
        return False
    attachment = parse_attachment(raw_attachment)
    if not attachment.is_pdf:
        return False
    link_mode = str(data.get("linkMode") or "").lower()
    path = str(data.get("path") or "")
    return link_mode in {"imported_file", "imported_url"} or path.startswith("storage:")


def attachment_reading_activity(
    raw_attachment: dict[str, Any],
    attachment_children: list[dict[str, Any]],
) -> ReadingActivity:
    activity = ReadingActivity(attachment_count=1)
    attachment = parse_attachment(raw_attachment)
    if attachment.is_pdf:
        activity.pdf_attachment_count = 1
    for child in attachment_children:
        data = child.get("data", child)
        if data.get("itemType") == "note":
            note = str(data.get("note") or "").strip()
            activity.note_count += 1
            activity.note_char_count += len(note)
        elif data.get("itemType") == "annotation":
            add_activity(activity, annotation_activity(child))
    return finalize_reading_activity(activity)


def _unsafe_reasons(activity: ReadingActivity, source_exists: bool) -> list[str]:
    reasons: list[str] = []
    if activity.has_reading_work:
        reasons.append("old-stored-attachment-has-reading-work")
    if not source_exists:
        reasons.append("stored-pdf-file-not-found")
    return reasons


def build_localize_attachments_plan(
    local_base_url: str = DEFAULT_LOCAL_API_BASE_URL,
    library_prefix: str = DEFAULT_LIBRARY_PREFIX,
    vault_library: Path = DEFAULT_VAULT_LIBRARY,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    seen: set[Path] = set()
    with ZoteroLocalClient(base_url=local_base_url, library_prefix=library_prefix) as client:
        for raw_parent in client.iter_top_items():
            parent_key = _key(raw_parent)
            raw_children = client.get_item_children(parent_key)
            stored_attachments = [
                child for child in raw_children if is_stored_pdf_attachment(child)
            ]
            if not stored_attachments:
                continue
            parsed_attachments = [parse_attachment(child) for child in stored_attachments]
            parent_item = parse_zotero_item(raw_parent, parsed_attachments)
            enriched_parent = enrich_item(parent_item)

            for raw_attachment in stored_attachments:
                attachment_key = _key(raw_attachment)
                data = raw_attachment.get("data", {})
                source_path = client.resolve_attachment_file_path(attachment_key)
                source = Path(source_path).expanduser() if source_path else None
                source_exists = bool(source and source.exists())
                attachment = parse_attachment(raw_attachment, str(source) if source else None)
                attachment_children = client.get_item_children(attachment_key)
                activity = attachment_reading_activity(raw_attachment, attachment_children)
                base_target = target_path_for_item(enriched_parent, vault_library)
                target = dedupe_target_path(base_target, seen, attachment_key)
                source_sha256 = sha256_file(source) if source_exists and source else None
                unsafe_reasons = _unsafe_reasons(activity, source_exists)

                items.append(
                    {
                        "parent_item_key": parent_key,
                        "parent_title": parent_item.title,
                        "attachment_key": attachment_key,
                        "attachment_version": _version(raw_attachment),
                        "attachment_title": attachment.title or data.get("title"),
                        "old_link_mode": data.get("linkMode"),
                        "old_path": data.get("path"),
                        "source_path": str(source) if source else None,
                        "source_exists": source_exists,
                        "source_sha256": source_sha256,
                        "target_path": str(target),
                        "target_exists": target.exists(),
                        "reading_activity": activity.model_dump(),
                        "unsafe_to_delete": bool(unsafe_reasons),
                        "unsafe_reasons": unsafe_reasons,
                        "planned_actions": [
                            "copy-stored-pdf-to-vault",
                            "create-linked-file-attachment",
                            "keep-old-stored-attachment",
                        ],
                    }
                )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vault_library": str(vault_library.expanduser()),
        "bridge_note": BRIDGE_NOTE,
        "items": items,
    }


def write_localize_attachments_report(plan: dict[str, Any], path: Path) -> None:
    ensure_parent_dir(path)
    unsafe = [item for item in plan["items"] if item["unsafe_to_delete"]]
    lines = [
        "# localize attachments report",
        "",
        f"- Stored PDF attachments found: {len(plan['items'])}",
        f"- Unsafe to delete without manual review: {len(unsafe)}",
        f"- Vault library: {plan['vault_library']}",
        "",
        plan["bridge_note"],
        "",
        "No old stored attachments are deleted by localization.",
        "",
        "## Attachments",
        "",
    ]
    for item in plan["items"]:
        unsafe_label = "yes" if item["unsafe_to_delete"] else "no"
        lines.append(
            f"- {item['attachment_key']} under {item['parent_item_key']} -> "
            f"`{item['target_path']}`; unsafe to delete: {unsafe_label}; "
            f"reasons: {', '.join(item['unsafe_reasons']) or 'none'}"
        )
    if not plan["items"]:
        lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plan_localize_attachments_file(
    output_path: Path,
    report_path: Path,
    local_base_url: str = DEFAULT_LOCAL_API_BASE_URL,
    library_prefix: str = DEFAULT_LIBRARY_PREFIX,
    vault_library: Path = DEFAULT_VAULT_LIBRARY,
) -> dict[str, Any]:
    try:
        plan = build_localize_attachments_plan(
            local_base_url=local_base_url,
            library_prefix=library_prefix,
            vault_library=vault_library,
        )
    except LocalAPIUnavailable as exc:
        raise RuntimeError(LOCAL_API_SETUP_MESSAGE) from exc
    dump_json_data(output_path, plan)
    write_localize_attachments_report(plan, report_path)
    return plan


def validate_localize_apply(
    apply: bool,
    confirm: str | None,
    user_id: str | None,
    api_key: str | None,
) -> None:
    if not apply:
        raise ValueError("Refusing to localize attachments: --apply is required.")
    if confirm != LOCALIZE_CONFIRMATION:
        raise ValueError(
            f'Refusing to localize attachments: --confirm "{LOCALIZE_CONFIRMATION}" is required.'
        )
    if not user_id or not api_key:
        raise ValueError("ZOTERO_USER_ID and ZOTERO_API_KEY must be set.")
    if not user_id.isdigit():
        raise ValueError("ZOTERO_USER_ID must be your numeric Zotero user ID.")


def copy_stored_pdf_to_vault(item: dict[str, Any]) -> str:
    source = Path(item["source_path"]).expanduser() if item.get("source_path") else None
    if source is None or not source.exists():
        raise FileNotFoundError(f"Stored PDF source missing for {item['attachment_key']}")
    target = Path(item["target_path"]).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        existing_sha = sha256_file(target)
        if item.get("source_sha256") and existing_sha == item["source_sha256"]:
            return existing_sha
        raise FileExistsError(f"Target exists with different content: {target}")
    shutil.copy2(source, target)
    actual = sha256_file(target)
    if item.get("source_sha256") and actual != item["source_sha256"]:
        target.unlink(missing_ok=True)
        raise ValueError(f"Checksum mismatch after copy: {target}")
    return actual


def parent_has_linked_path(
    client: ZoteroWebClient,
    parent_key: str,
    target_path: str,
    vault_library: Path = DEFAULT_VAULT_LIBRARY,
) -> str | None:
    target = Path(target_path).expanduser()
    acceptable_paths = {
        str(target.resolve(strict=False)),
        zotero_linked_attachment_path(target, vault_library=vault_library),
    }
    for child in client.get_item_children(parent_key):
        data = child.get("data", {})
        if data.get("itemType") != "attachment":
            continue
        if data.get("linkMode") == "linked_file" and str(data.get("path")) in acceptable_paths:
            return str(child.get("key") or data.get("key"))
    return None


def apply_localize_attachments_plan(
    plan: dict[str, Any],
    user_id: str,
    api_key: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    vault_library = Path(plan["vault_library"]).expanduser()
    with ZoteroWebClient(user_id=user_id, api_key=api_key) as client:
        for item in plan["items"]:
            checksum = copy_stored_pdf_to_vault(item)
            events.append(
                {
                    "event": "stored-pdf-copied-to-vault",
                    "attachmentKey": item["attachment_key"],
                    "targetPath": item["target_path"],
                    "sha256": checksum,
                    "unsafeToDelete": item["unsafe_to_delete"],
                }
            )
            existing_linked_key = parent_has_linked_path(
                client,
                item["parent_item_key"],
                item["target_path"],
                vault_library=vault_library,
            )
            if existing_linked_key:
                events.append(
                    {
                        "event": "linked-attachment-already-exists",
                        "parentItemKey": item["parent_item_key"],
                        "attachmentKey": existing_linked_key,
                        "path": item["target_path"],
                    }
                )
                continue
            response = client.post_items(
                [
                    linked_attachment_body(
                        item["parent_item_key"],
                        Path(item["target_path"]).expanduser(),
                        title=item.get("attachment_title") or item.get("parent_title"),
                        vault_library=vault_library,
                    )
                ]
            )
            linked_key = _created_key(response.json())
            events.append(
                {
                    "event": "linked-attachment-created",
                    "parentItemKey": item["parent_item_key"],
                    "oldStoredAttachmentKey": item["attachment_key"],
                    "linkedAttachmentKey": linked_key,
                    "path": item["target_path"],
                    "statusCode": response.status_code,
                }
            )
    return events


def write_apply_log(events: list[dict[str, Any]], prefix: str = "localize_apply_log") -> tuple[Path, Path]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = Path(f"data/{prefix}_{ts}.json")
    md_path = Path(f"data/{prefix}_{ts}.md")
    dump_json_data(json_path, {"events": events})
    ensure_parent_dir(md_path)
    lines = [f"# {prefix.replace('_', ' ')}", ""]
    lines.extend(f"- {event['event']}: {event}" for event in events)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def _load_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def linked_attachment_exists(
    parent_key: str,
    target_path: str,
    vault_library: Path = DEFAULT_VAULT_LIBRARY,
    user_id: str | None = None,
    api_key: str | None = None,
) -> bool:
    if user_id and api_key:
        with ZoteroWebClient(user_id=user_id, api_key=api_key) as client:
            return bool(parent_has_linked_path(client, parent_key, target_path, vault_library))
    target = Path(target_path).expanduser()
    acceptable_paths = {
        str(target.resolve(strict=False)),
        zotero_linked_attachment_path(target, vault_library=vault_library),
    }
    try:
        with ZoteroLocalClient() as client:
            for child in client.get_item_children(parent_key):
                data = child.get("data", {})
                if data.get("itemType") == "attachment" and data.get("linkMode") == "linked_file":
                    if str(data.get("path")) in acceptable_paths:
                        return True
    except Exception:
        return False
    return False


def build_localize_verify_report(
    plan: dict[str, Any],
    user_id: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    vault_library = Path(plan["vault_library"]).expanduser()
    for item in plan["items"]:
        target = Path(item["target_path"]).expanduser()
        source = Path(item["source_path"]).expanduser() if item.get("source_path") else None
        linked_exists = target.exists()
        checksum_ok = (
            linked_exists
            and bool(item.get("source_sha256"))
            and sha256_file(target) == item["source_sha256"]
        )
        old_stored_exists = bool(source and source.exists())
        parent_has_linked = linked_attachment_exists(
            item["parent_item_key"],
            item["target_path"],
            vault_library=vault_library,
            user_id=user_id,
            api_key=api_key,
        )
        ok = bool(linked_exists and checksum_ok and old_stored_exists and parent_has_linked)
        rows.append(
            {
                "parent_item_key": item["parent_item_key"],
                "attachment_key": item["attachment_key"],
                "target_path": item["target_path"],
                "linked_file_exists": linked_exists,
                "checksum_ok": checksum_ok,
                "old_stored_file_exists": old_stored_exists,
                "parent_has_linked_pdf": parent_has_linked,
                "unsafe_to_delete": item["unsafe_to_delete"],
                "ok": ok,
            }
        )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": rows,
    }


def write_verify_report(report: dict[str, Any], json_path: Path, md_path: Path) -> None:
    dump_json_data(json_path, report)
    ensure_parent_dir(md_path)
    ok_count = sum(1 for item in report["items"] if item["ok"])
    lines = [
        "# localize verify report",
        "",
        f"- Verified attachments: {len(report['items'])}",
        f"- OK: {ok_count}",
        "",
        "## Items",
        "",
    ]
    for item in report["items"]:
        lines.append(
            f"- {item['attachment_key']}: ok={item['ok']}, "
            f"linked file exists={item['linked_file_exists']}, "
            f"checksum ok={item['checksum_ok']}, "
            f"old stored exists={item['old_stored_file_exists']}, "
            f"parent has linked PDF={item['parent_has_linked_pdf']}, "
            f"unsafe to delete={item['unsafe_to_delete']}"
        )
    if not report["items"]:
        lines.append("- None")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify_localized_attachments_file(
    plan_path: Path,
    json_output: Path,
    markdown_output: Path,
    user_id: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    plan = _load_json(plan_path)
    report = build_localize_verify_report(plan, user_id=user_id, api_key=api_key)
    write_verify_report(report, json_output, markdown_output)
    return report


def validate_cleanup_stored_request(
    apply: bool,
    confirm: str | None,
    verify_path: Path,
    user_id: str | None,
    api_key: str | None,
) -> None:
    if not apply:
        return
    if confirm != CLEANUP_STORED_CONFIRMATION:
        raise ValueError(
            f'Refusing cleanup: --confirm "{CLEANUP_STORED_CONFIRMATION}" is required.'
        )
    if not verify_path.exists():
        raise ValueError("Refusing cleanup: verify report is missing.")
    if not user_id or not api_key:
        raise ValueError("ZOTERO_USER_ID and ZOTERO_API_KEY must be set.")
    if not user_id.isdigit():
        raise ValueError("ZOTERO_USER_ID must be your numeric Zotero user ID.")


def build_cleanup_stored_report(
    plan: dict[str, Any],
    verify_report: dict[str, Any] | None,
) -> dict[str, Any]:
    verify_by_key = {
        item["attachment_key"]: item for item in (verify_report or {}).get("items", [])
    }
    rows: list[dict[str, Any]] = []
    for item in plan["items"]:
        verify = verify_by_key.get(item["attachment_key"])
        blockers: list[str] = []
        if verify is None:
            blockers.append("verify-report-missing-for-attachment")
        else:
            if not verify["linked_file_exists"]:
                blockers.append("linked-file-missing")
            if not verify["checksum_ok"]:
                blockers.append("checksum-mismatch")
            if not verify["old_stored_file_exists"]:
                blockers.append("old-stored-file-missing")
            if not verify["parent_has_linked_pdf"]:
                blockers.append("parent-missing-linked-pdf")
        if item["unsafe_to_delete"]:
            blockers.extend(item["unsafe_reasons"])
        rows.append(
            {
                "attachment_key": item["attachment_key"],
                "attachment_version": item.get("attachment_version"),
                "parent_item_key": item["parent_item_key"],
                "target_path": item["target_path"],
                "can_delete_old_stored_attachment": not blockers,
                "blockers": blockers,
            }
        )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": rows,
    }


def write_cleanup_stored_report(report: dict[str, Any], json_path: Path, md_path: Path) -> None:
    dump_json_data(json_path, report)
    ensure_parent_dir(md_path)
    allowed = sum(1 for item in report["items"] if item["can_delete_old_stored_attachment"])
    lines = [
        "# stored attachment cleanup report",
        "",
        f"- Old stored attachments reviewed: {len(report['items'])}",
        f"- Eligible for deletion: {allowed}",
        "",
        "This report never deletes parent items or linked vault files.",
        "",
        "## Items",
        "",
    ]
    for item in report["items"]:
        lines.append(
            f"- {item['attachment_key']}: can delete={item['can_delete_old_stored_attachment']}; "
            f"blockers: {', '.join(item['blockers']) or 'none'}"
        )
    if not report["items"]:
        lines.append("- None")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_cleanup_stored_report(
    report: dict[str, Any],
    user_id: str,
    api_key: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with ZoteroWebClient(user_id=user_id, api_key=api_key) as client:
        for item in report["items"]:
            if not item["can_delete_old_stored_attachment"]:
                events.append(
                    {
                        "event": "stored-attachment-delete-skipped",
                        "attachmentKey": item["attachment_key"],
                        "blockers": item["blockers"],
                    }
                )
                continue
            response = client.delete_item(
                item["attachment_key"],
                version=item.get("attachment_version"),
            )
            events.append(
                {
                    "event": "old-stored-attachment-deleted",
                    "attachmentKey": item["attachment_key"],
                    "parentItemKey": item["parent_item_key"],
                    "statusCode": response.status_code,
                    "linkedVaultFilePreserved": item["target_path"],
                }
            )
    return events


def cleanup_stored_attachments_file(
    plan_path: Path,
    verify_path: Path,
    json_output: Path,
    markdown_output: Path,
    apply: bool = False,
    user_id: str | None = None,
    api_key: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    plan = _load_json(plan_path)
    verify = _load_json(verify_path) if verify_path.exists() else None
    report = build_cleanup_stored_report(plan, verify)
    write_cleanup_stored_report(report, json_output, markdown_output)
    if not apply:
        return report, []
    events = apply_cleanup_stored_report(report, user_id or "", api_key or "")
    return report, events
