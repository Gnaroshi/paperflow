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
