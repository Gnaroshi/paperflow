# PaperFlow UI/UX Verification Checklist

This checklist is the acceptance contract for every PaperFlow visual component.
Run it at 760x620, 900x700, and 1180x820 main-window sizes. Test PFW in idle,
queued, processing, success, failure, Status, Recent, Zotero, and Logs modes.

## Global Layout

- [x] No text, control, badge, or button overlaps another element.
- [x] No control extends beyond the visible trailing or bottom edge.
- [x] Every long page owns vertical scrolling and opens at scroll position zero.
- [x] Wide tables own horizontal scrolling without widening the parent view.
- [x] Footer actions remain visible and never cover scroll content.
- [x] Fixed-width dialogs fit inside the minimum supported screen/window.
- [x] Sidebar rail remains 52 pt and its toggle stays anchored top-left.
- [x] Header actions collapse to icons before they can clip.

## Visual Hierarchy

- [x] Screen title, purpose, primary workflow, results, and details are distinct.
- [x] Base surfaces occupy most of the screen; gradients remain accents only.
- [x] Nested decorative cards are avoided.
- [x] Section boundaries remain visible without heavy outlines.
- [x] Primary, secondary, destructive, disabled, and blocked actions are distinct.
- [x] Muted text remains legible against every background.
- [x] Empty space supports grouping and does not separate related controls.

## User-facing Information Boundary

- [x] Default navigation hides Logs and developer-only surfaces.
- [x] Dashboard does not show repository paths, raw provider values, commands, or repeated sync prose.
- [x] PFW hides Logs, PID, command, working directory, raw output, artifact names, and storage internals by default.
- [x] Local Folder Import hides paths, item keys, confidence, raw match reasons, and temporary overrides by default.
- [x] Settings exposes one opt-in Advanced & Diagnostics boundary for paths, raw status, reports, and logs.
- [x] User Guide contains no CLI command, config path, artifact filename, or developer workflow.
- [x] Errors retain a plain summary, preserved state, recovery action, and optional diagnostic detail.
- [x] Focused copy and mode-filter tests prevent technical detail from returning to default UI.

## Interaction and State

- [x] Every button has a visible purpose and predictable result.
- [x] Ordered workflows show step number, prerequisite, state, and output.
- [x] Blocked actions show the exact missing prerequisite.
- [x] A failed/cancelled sequence never starts dependent commands.
- [x] Dry-run and apply actions are separated and clearly labelled.
- [x] Disabled controls do not retain misleading primary emphasis.
- [x] Errors remain visible until dismissed.
- [x] Running commands expose stage, elapsed time, log, and cancellation.

## Accessibility

- [x] Essential state uses icon + text + color, never color alone.
- [x] Interactive targets are at least 30 pt high.
- [x] Icon-only buttons have help/accessibility labels.
- [x] Text fields have visible labels or unambiguous placeholders.
- [x] Keyboard navigation reaches primary actions in logical order.
- [x] Segmented controls use labels that fit at minimum width.
- [x] Secrets appear only as secure fields or redacted values.

## Settings Form Alignment

- [x] Every setting uses the shared label/detail and control columns.
- [x] Pickers, text fields, sliders, and steppers share one control width.
- [x] Boolean values use trailing switches on the same alignment axis.
- [x] Dependent hot-zone controls appear only while hot-zone is enabled.
- [x] Preview and diagnostic commands live in a separate action bar.
- [x] Rows reflow to label-over-control when 604 pt cannot fit.
- [x] Settings spacing uses `PaperFlowSpacing` tokens instead of local gaps.

## Component Matrix

### Main Window

- [x] `MainWindowView`: minimum size, scroll reset, content gutter, log dock.
- [x] `SidebarRailOrFullSidebar`: expanded/rail selection and stable toggle.
- [x] `HeaderView`: compact icon mode and no trailing clipping.
- [x] `PersistentNotice`: wraps long errors and remains dismissible.
- [x] `CommandActivityDock`: collapsed/running/expanded states.
- [x] Confirmation sheets: routine Apply uses current preview/backup gates; irreversible cleanup retains exact text.

### Primary Tabs

- [x] `DashboardView`: compact hero, account status, metrics, status cards.
- [x] `DropShelfSettingsView`: grouped settings and wrapped action controls.
- [x] `ZoteroOrganizeView`: five planning steps and separate apply section.
- [x] `LocalVaultView`: status, instructions, prerequisites, actions.
- [x] `LocalFolderImportView`: source, policy, six steps, filters, wide table.
- [x] `ExistingAttachmentsView`: plan/apply/verify and cleanup danger section.
- [x] `CleanupWorkbenchView`: toolbar, search, tabs, cards, duplicate actions.
- [x] `ReportsView`: available/missing status and safe open behavior.
- [x] `SettingsView`: narrow label-over-control layout and secure fields.
- [x] `UserGuideView`: readable Korean instructions and scrolling.
- [x] `LogsView`: current status, output surface, copy/open/stop controls.

### Floating UI

- [x] `DropShelfPanel`: no titlebar border, shadow only, receives mouse events.
- [x] `DropShelfView` header: title, mode control, close button all fit.
- [x] Drop mode: target, files, action, safety options, confirmation, footer fit.
- [x] Status mode: all status tiles and sync note are visible.
- [x] Recent mode: plan summary and report/vault actions are reachable.
- [x] Zotero mode: actions wrap and ingest-only footer is hidden.
- [x] Logs mode: command, log tail, and log actions fit.
- [x] Processing/result modes: timeline/result content does not hide footer.
- [x] Compact pill: click, double-click, context menu, drag activation.
- [x] `CommandPopupWindow`: frame is capped to the active visible screen.
- [x] `CommandPaletteView`: search, list, keyboard selection, footer, close.

## Recurrent Review Log

### Pass 1 - Inventory and minimum-window inspection

- [x] Inspected all SwiftUI view declarations and fixed frame usage.
- [x] Inspected every main-window tab at the minimum saved window size.
- [x] Confirmed no main-tab horizontal overlap.
- [x] Found PFW idle/status/recent content clipping and compressed action label.
- [x] Found Drop Shelf Settings and Logs lack clear section grouping.
- [x] Found Reports does not distinguish available and missing artifacts.

### Pass 2 - PFW and settings remediation

- [x] Rebuild and inspect every changed main-window component.
- [x] Inspect all five PFW modes after adaptive sizing/footer changes.
- [x] Inspect processing, success, and failure layout paths and completion parsing.
- [x] Inspect Command Popup at visible-frame limits.

Findings resolved: the drop action label no longer compresses vertically, non-drop
modes no longer inherit ingest controls, and every PFW size is capped to the active
screen's `visibleFrame`. Processing and result layouts use adaptive grids and wrapped
actions so the footer remains reachable.

### Pass 3 - Main-window visual regression

- [x] Inspect Dashboard, Drop Shelf Settings, Zotero Organize, and Local Vault.
- [x] Inspect Local Folder Import, Existing Attachments, and Cleanup Workbench.
- [x] Inspect User Guide, Reports, Settings, and Logs.
- [x] Confirm workflow prerequisites and blocked reasons remain visible.
- [x] Confirm the 52 pt collapsed sidebar rail keeps its toggle anchored left.

Findings resolved: settings, vault, reports, and logs now use explicit sections;
missing reports are disabled and labelled; ordered workflows expose prerequisites;
and wide import data scrolls within its own table region.

### Pass 4 - Golden ingest and result regression

- [x] Run `2606.18208v1.pdf` through default dry-run without Gemini.
- [x] Confirm progress JSONL reaches `done` and exits with code 0.
- [x] Confirm the run completes in under the configured timeout.
- [x] Confirm `ingest_plan.json` reports linked-local storage and no cloud upload.
- [x] Confirm title, arXiv ID, abstract, collections, tags, and filename.

Finding resolved: the arXiv Atom feed title was being mistaken for the entry title.
The parser now reads the first Atom `entry`, rejects stale feed titles in cache, and
falls back to the extracted PDF title when cached metadata is invalid.

### Pass 5 - Release regression

- [x] Run Swift build, Python tests, Ruff, and shell validation.
- [x] Build/install the application and repeat minimum-window screenshots.
- [x] Confirm Spotlight-installed app matches the validated build.
- [x] Confirm PFW is absent at launch and can be hidden from its header control.
- [x] Confirm the installed PFW Drop and Status modes remain inside the screen.

### Pass 6 - MDS settings alignment

- [x] Read `gnaroshi_mds/guides/ui-ux.md` and `guides/application.md`.
- [x] Convert Settings and Drop Shelf Settings to shared semantic rows.
- [x] Align switches, selectors, fields, steppers, sliders, and action bars by role.
- [x] Add progressive disclosure for disabled hot-zone controls.
- [x] Build, Developer ID sign, install, and validate the resulting component tree.

### Pass 7 - Storage role and Zotero import model

- [x] Separate managed write vault, Zotero-managed storage, and import sources.
- [x] Show existing Zotero storage without treating it as a writable PaperFlow vault.
- [x] Expose Downloads as a dry-run local import source.
- [x] State that Add to Zotero creates the parent item and linked attachment.
- [x] Pass the selected managed vault path to every ingest/import/localization plan.
- [x] Preserve Zotero stored attachments and reading work by default.
