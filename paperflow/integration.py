from __future__ import annotations

import json
import os
import hashlib
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import typer
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from paperflow import __version__


INTEGRATION_SCHEMA_VERSION = 1
INTEGRATION_CONTRACT_VERSION = 1
PROVIDER_ID = "paperflow"


def build_provenance() -> dict[str, Any]:
    """Return path-free Git provenance for source and packaged builds."""

    commit = os.environ.get("PAPERFLOW_BUILD_COMMIT")
    count = os.environ.get("PAPERFLOW_BUILD_NUMBER")
    dirty: bool | None = None
    root = Path(__file__).resolve().parents[1]
    if not commit and (root / ".git").exists():
        try:
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            ).stdout.strip()
            count = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            ).stdout.strip()
            dirty = bool(
                subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=2,
                ).stdout.strip()
            )
        except (OSError, subprocess.SubprocessError):
            commit = None
            count = None
    return {
        "commit": commit if commit and re.fullmatch(r"[0-9a-f]{40}", commit) else None,
        "number": int(count) if count and count.isdigit() else None,
        "dirty": dirty,
    }


class ProviderInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Literal["paperflow"] = PROVIDER_ID
    version: str = __version__
    contract_version: Literal[1] = Field(
        INTEGRATION_CONTRACT_VERSION, alias="contractVersion"
    )


class IntegrationError(BaseModel):
    code: str
    message: str


class IntegrationEnvelope(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: Literal[1] = Field(
        INTEGRATION_SCHEMA_VERSION, alias="schemaVersion"
    )
    provider: ProviderInfo = Field(default_factory=ProviderInfo)
    capability: str
    generated_at: str = Field(alias="generatedAt")
    status: Literal[
        "ok", "partial", "blocked", "unavailable", "stale", "incompatible", "failed"
    ]
    data: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    errors: list[IntegrationError] = Field(default_factory=list)


def integration_envelope(
    capability: str,
    *,
    status: Literal[
        "ok", "partial", "blocked", "unavailable", "stale", "incompatible", "failed"
    ] = "ok",
    data: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    errors: list[IntegrationError] | None = None,
) -> IntegrationEnvelope:
    return IntegrationEnvelope(
        capability=capability,
        generatedAt=datetime.now(timezone.utc).isoformat(),
        status=status,
        data=data or {},
        warnings=warnings or [],
        errors=errors or [],
    )


def emit_json(envelope: IntegrationEnvelope) -> None:
    typer.echo(envelope.model_dump_json(by_alias=True, exclude_none=True))


def emit_json_failure(
    capability: str,
    *,
    code: str,
    message: str,
    status: Literal["blocked", "unavailable", "failed"] = "failed",
    exit_code: int = 2,
) -> None:
    emit_json(
        integration_envelope(
            capability,
            status=status,
            errors=[IntegrationError(code=code, message=message)],
        )
    )
    typer.echo(f"PaperFlow {capability} failed: {code}", err=True)
    raise typer.Exit(exit_code)


def artifact_name(path: Path) -> str:
    return path.name


def artifact_state(path: Path) -> Literal["available", "missing"]:
    return "available" if path.is_file() else "missing"


def status_data(data_dir: Path = Path("data")) -> dict[str, Any]:
    return {
        "availability": "available",
        "capabilities": [
            "scan-library",
            "plan-organization",
            "import-paper",
            "open-paper",
            "open-plan",
        ],
        "artifacts": {
            "zoteroScan": artifact_state(data_dir / "zotero_items.jsonl"),
            "organizationPlan": artifact_state(data_dir / "organize_plan.json"),
            "ingestPlan": artifact_state(data_dir / "ingest_plan.json"),
        },
        "safety": {
            "zoteroLocalApi": "read-only",
            "zoteroSqlite": "never-edited",
            "automaticDelete": False,
            "automaticRename": False,
            "writeBoundary": "explicit-apply",
            "defaultMode": "dry-run",
        },
    }


def recent_activity_data(data_dir: Path = Path("data"), *, limit: int = 5) -> dict[str, Any]:
    if not 1 <= limit <= 20:
        raise ValueError("Recent activity limit must be between 1 and 20")
    candidates = [
        ("zotero-scan", "Zotero scan available", data_dir / "zotero_items.jsonl"),
        ("organization-plan", "Organization plan ready for review", data_dir / "organize_plan.json"),
        ("ingest-plan", "Import plan ready for review", data_dir / "ingest_plan.json"),
    ]
    activities: list[dict[str, Any]] = []
    for kind, summary, path in candidates:
        if not path.is_file():
            continue
        occurred_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        activities.append(
            {
                "id": f"paperflow:{kind}:{int(path.stat().st_mtime)}",
                "type": "next-action",
                "summary": summary,
                "occurredAt": occurred_at,
                "resourceId": kind,
                "actionable": kind != "zotero-scan",
            }
        )
    activities.sort(key=lambda item: item["occurredAt"], reverse=True)
    return {"activities": activities[:limit], "activityCount": min(len(activities), limit)}


def doctor_data(*, local_api_available: bool) -> tuple[str, dict[str, Any], list[str]]:
    web_credentials_configured = bool(
        os.environ.get("ZOTERO_USER_ID") and os.environ.get("ZOTERO_API_KEY")
    )
    checks = [
        {
            "id": "zotero-local-api",
            "status": "ok" if local_api_available else "blocked",
            "requiredFor": ["scan-library"],
        },
        {
            "id": "zotero-web-credentials",
            "status": "configured" if web_credentials_configured else "not-configured",
            "requiredFor": ["explicit-apply-only"],
        },
    ]
    warnings = [] if local_api_available else [
        "Start Zotero and enable its Local API before scanning."
    ]
    return ("ok" if local_api_available else "blocked"), {"checks": checks}, warnings


def json_round_trip(value: IntegrationEnvelope) -> dict[str, Any]:
    """Test helper that proves the emitted contract is one JSON value."""

    return json.loads(value.model_dump_json(by_alias=True, exclude_none=True))


class MetadataCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    title: str | None = Field(default=None, max_length=500)
    authors: list[str] = Field(default_factory=list, max_length=200)
    year: int | None = Field(default=None, ge=1600, le=2200)
    doi: str | None = Field(default=None, max_length=300)
    arxiv_id: str | None = Field(default=None, alias="arxivId", max_length=80)
    url: HttpUrl | None = None

    @model_validator(mode="after")
    def require_identity(self) -> "MetadataCandidate":
        if not any((self.title, self.doi, self.arxiv_id, self.url)):
            raise ValueError("Metadata candidate requires a title or stable identifier")
        return self


def stable_source_id(source_type: str, value: str) -> str:
    return f"{source_type}:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


def validate_arxiv_id(value: str) -> str:
    normalized = value.strip()
    if not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+\/\d{7})(?:v\d+)?", normalized, flags=re.I):
        raise ValueError("Invalid arXiv identifier")
    return normalized


def planned_handoff_changes(source_type: str) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = [
        {"kind": "review-metadata", "executed": False},
        {"kind": "create-or-match-zotero-parent", "executed": False},
    ]
    if source_type == "file":
        changes.extend(
            [
                {"kind": "copy-pdf-to-managed-vault", "executed": False},
                {"kind": "create-linked-local-attachment", "executed": False},
            ]
        )
    else:
        changes.append({"kind": "select-or-import-pdf", "executed": False})
    return changes
