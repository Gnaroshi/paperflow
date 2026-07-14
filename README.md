# paperflow

`paperflow` is a Python CLI for safely planning a reorganization of a Zotero
library of AI papers.

Safety defaults:

- It never edits `zotero.sqlite`.
- It never renames files.
- It never deletes Zotero items.
- It ignores existing Zotero collections when classifying papers.
- It uses the Zotero Local API only for read-only scanning.
- It defaults to dry-run behavior.
- Any future write operation must require `--apply`.

The first implementation can scan, plan, and report without a Zotero Web API key.
The `apply-plan` command is intentionally disabled until a Web API backend is
configured.

## Install

```bash
uv sync --extra dev
```

## Zotero Local API

Start Zotero Desktop and enable local API access:

1. Open Zotero settings/preferences.
2. Go to Advanced.
3. Enable local communication for other applications on this computer.
4. Keep Zotero running while scanning.

The default local API base URL is:

```text
http://localhost:23119/api/
```

## Commands

Scan Zotero through the read-only local API:

```bash
uv run paperflow zotero scan
```

Create an organization plan with no side effects:

```bash
uv run paperflow zotero plan-organize
```

Generate Markdown and CSV reports:

```bash
uv run paperflow zotero report
```

Preview planned Web API calls without writing:

```bash
uv run paperflow zotero apply-plan --mode add-only
```

The apply command refuses to write unless `--apply`, `ZOTERO_USER_ID`, and
`ZOTERO_API_KEY` are present, and the write backend remains disabled in this
version.

## Gnaroshi Studio integration

PaperFlow remains independently runnable. Studio uses the provider-owned
`gnaroshi.app.json` and fixed read-only or dry-run commands:

```bash
paperflow version --json
paperflow status --json
paperflow doctor --json
paperflow zotero scan --json
paperflow zotero plan-organize --json
paperflow import --file /user/selected/paper.pdf --dry-run --json
paperflow import --url https://example.org/paper --dry-run --json
paperflow import --arxiv 2401.00001 --dry-run --json
paperflow import --metadata /user/selected/candidate.json --dry-run --json
```

JSON mode emits one schema-v1 object on stdout and sends generic diagnostics to
stderr. The import command has no apply mode: it returns a preview disposition
and planned changes, then requires review in PaperFlow. Studio never reads or
writes Zotero, the managed vault, PaperFlow credentials, or internal reports
directly.

See `docs/decisions/MDS-001-studio-integration.md` for preservation,
compatibility, tests, and rollback.
