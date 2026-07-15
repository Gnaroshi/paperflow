# PaperFlow macOS App

PaperFlow is a local-first macOS utility for the existing `paperflow` Python
CLI. The primary PDF UI is a shortcut-triggered floating drop shelf with
optional screen-edge hot-zones, plus a Raycast-style command window and a full
control-panel window.
The app does not classify papers or rewrite Zotero logic in Swift. It passes
commands and paths to the CLI, parses local reports, and keeps apply operations
behind typed confirmations.

## Local-first Zotero model

- Zotero keeps metadata, collections, tags, notes, and annotations.
- PDFs should live in the local PaperFlow vault by default.
- PDF upload to Zotero Storage is not a default workflow.
- Existing notes, highlights, underlines, annotations, and child notes must not
  be deleted automatically.
- Data sync and file sync are separate in Zotero.
- For local-only PDFs, Zotero file sync should be off to avoid the 300 MB free
  storage limit.
- When PaperFlow writes through the Zotero Web API, Zotero Desktop needs data
  sync enabled or a manual sync to show the changes.

## Build

From this directory:

```bash
swift build -c release
./build_app.sh
open dist/PaperFlow.app
```

Local bundles prefer the installed Developer ID identity so the signing team
matches public releases; they fall back to Apple Development when necessary.
Keep the bundle ID and installed path stable, then test protected-folder
access through the installed app rather than `swift run`. This prevents each
rebuild from becoming a new ad-hoc code identity; macOS may still require approval
for a newly requested protected resource or entitlement.

`build_app.sh` creates:

- `dist/PaperFlow.app`
- `dist/PaperFlow.zip`
- `dist/PaperFlow.dmg`

For local Spotlight launch, install the app into `/Applications`:

```bash
./install_app.sh
```

Then press `Command-Space`, type `PaperFlow`, and press Return.

For GitHub download distribution, upload `dist/PaperFlow.zip` and
`dist/PaperFlow.dmg` to a release. The DMG is the normal macOS
drag-to-Applications download.

Check whether this Mac is ready for Developer ID distribution:

```bash
./distribution_check.sh
```

If Developer ID signing credentials are available:

```bash
SIGNING_MODE=release \
DEVELOPER_ID_APPLICATION="Developer ID Application: YOUR NAME (TEAMID)" \
./build_app.sh
```

For notarization:

```bash
SIGNING_MODE=release \
DEVELOPER_ID_APPLICATION="Developer ID Application: YOUR NAME (TEAMID)" \
NOTARY_PROFILE="paperflow-notary" \
./build_app.sh
```

The app bundle contains `gnaroshi.app.json` and path-free Git build provenance.
GitHub release packaging must upload the manifest beside the ZIP/DMG. Source
checkouts may fetch remote refs, but update tooling must not merge, reset, or
replace a dirty worktree automatically.

## Set Up

Open PaperFlow from Spotlight after running `./install_app.sh`, or directly
from `dist/PaperFlow.app` during development. The menu bar item is only for
status/settings/actions; it is not the PDF drop surface. Use Settings for:

- `PaperFlow project directory`: the folder containing `pyproject.toml`
- `uv path`: use the repo-local `bin/paperflow-uv` wrapper. Run
  `scripts/bootstrap_uv.sh` once to copy the uv binary into
  `.paperflow/bin/uv`. The wrapper isolates `.venv`, uv cache, downloaded
  Python versions, and uv tools inside this repository.
- `local vault path`: default `~/Papers/Paperflow/Library`
- Zotero API key: stored in macOS Keychain and redacted in logs
- Numeric Zotero user ID: fetch from the Zotero API key; email addresses and
  usernames do not work for Zotero Web API write URLs
- Gemini API key and model: optional, stored in Keychain, used only for
  explicitly enabled cleanup assistance

The app sets a broad `PATH` before running commands so Finder, Spotlight, and
Login Items launches behave like a shell launch.

## Install uv

```bash
brew install uv
uv --version
```

## Manual CLI Commands

From the paperflow project directory:

```bash
uv run paperflow zotero backup
uv run paperflow zotero enrich-metadata
uv run paperflow zotero detect-duplicates
uv run paperflow zotero plan-migration
uv run paperflow zotero dry-run-migration
uv run paperflow zotero apply-migration --collection-mode replace-all --tag-mode replace-managed --apply --confirm "REPLACE MY ZOTERO COLLECTIONS"
uv run paperflow zotero cleanup-collections --mode report-only
uv run paperflow vault init
uv run paperflow vault plan-paths
uv run paperflow zotero plan-localize-attachments
uv run paperflow zotero apply-localize-attachments --apply --confirm "LOCALIZE ZOTERO PDF ATTACHMENTS"
uv run paperflow zotero verify-localized-attachments
uv run paperflow zotero cleanup-stored-attachments
uv run paperflow credentials zotero verify
uv run paperflow credentials gemini verify --model gemini-2.5-flash
uv run paperflow cleanup repair-abstracts --dry-run
uv run paperflow cleanup repair-metadata --dry-run
uv run paperflow cleanup plan-duplicates
uv run paperflow zotero migration-audit
```

## App Sections

- Dashboard: project, Zotero, migration, cleanup, vault, duplicate, and metadata
  status from local files under `data/`.
- Drop Shelf Settings: activation mode, shortcut, placement, monitor mode,
  optional hot-zone, opacity, and collapse timing.
- Zotero Organize: backup, enrich metadata, detect duplicates, plan migration,
  dry run, and confirmed apply migration.
- Local Vault: vault status, initialization, and vault path planning.
- Existing Attachments: workflows for localizing stored Zotero PDFs.
- Cleanup Workbench: Missing Abstract, Missing Metadata, Duplicate Candidates,
  Low Confidence, and Non-paper review surfaces. It reads local plans/reports
  and calls backend cleanup commands. Missing Abstract and Missing Metadata
  support selected-item dry runs and selected-item applies through backend
  `--item-key`; metadata repair can constrain writes with `--approved-field`.
- Reports: opens migration, preview, cleanup, dedupe, localization, and apply
  log reports.
- Settings: paths, hot-zone preferences, shortcuts, Zotero credentials, Gemini
  credentials/quota status, local vault, collection mode, tag mode, and cleanup
  safety defaults.
- Logs: command output and app logs.

## Drag and Drop

Press `Control + Shift + Command + Plus` (`⌃⇧⌘+`) to raise the drop shelf from
the bottom center of the focused monitor. Drag `.pdf` files onto the shelf.
Optional hot-zone activation can be enabled in Settings. Non-PDF files are
rejected with a visible warning. Linked-local ingest copies PDFs into the local
vault and creates Zotero linked attachment records:

```bash
uv run paperflow ingest <pdf_paths> --dry-run --storage-mode linked-local
uv run paperflow ingest <pdf_paths> --apply --storage-mode linked-local
```

No PDF bytes are uploaded to Zotero Storage.

Default shortcuts:

- Option + Space: command window
- Control + Shift + Command + Plus: show/hide drop shelf
- Option + Shift + I: Finder selection ingest placeholder

## Safety

Apply Migration requires typing:

```text
REPLACE MY ZOTERO COLLECTIONS
```

PDF ingest apply requires typing:

```text
INGEST LOCAL PDFS
```

Stored attachment cleanup requires typing:

```text
DELETE OLD STORED PDF ATTACHMENTS
```

Abstract and metadata cleanup applies require typing:

```text
APPLY ABSTRACT REPAIRS
APPLY METADATA REPAIRS
```

The app writes its own logs to:

```text
~/Library/Logs/PaperFlow/
```

Secrets are redacted from displayed and saved command output.

## Troubleshooting

### Keychain or Desktop permission appears after every rebuild

PaperFlow needs a stable Apple code-signing identity. An ad-hoc signature changes
whenever the executable is rebuilt, so macOS can treat the next build as a different
application even though the bundle identifier remains `com.paperflow.app`. Keychain
"Always Allow" and Files & Folders consent then apply only to the previous build.

1. Open Xcode -> Settings -> Accounts and select the Apple Developer account.
2. Open Manage Certificates and create or download an Apple Development certificate
   for local builds. Use Developer ID Application for public distribution.
3. Confirm `security find-identity -v -p codesigning` lists the certificate.
4. Run `./build_app.sh`. It automatically prefers Developer ID Application, then
   Apple Development. `PAPERFLOW_SIGNING_IDENTITY` can select one explicitly.
5. Install the newly signed app, open it once, and approve Keychain and Desktop access.

The current PaperFlow project is under `~/Desktop`, which is a macOS protected
folder. Keeping the project under `~/Developer` avoids Desktop-folder consent. If it
stays on Desktop, a stable signature allows the approval to survive future builds.

- If `uv` cannot be found, set the full executable path in Settings.
- If Zotero Web API calls fail, verify that `ZOTERO_USER_ID` is numeric and the
  API key has write permissions.
- If Zotero Desktop does not show Web API changes, trigger Zotero data sync.
- If PDFs are consuming Zotero Storage, check Zotero file sync settings.
- If drag-and-drop paths cannot be read, move files into a user-owned folder
  such as Downloads, Documents, or the PaperFlow vault.
- If Spotlight cannot find PaperFlow immediately after install, wait a few
  seconds for Spotlight indexing, or run `./install_app.sh` again.
- If launch at login fails, add `/Applications/PaperFlow.app` manually in macOS
  System Settings.
