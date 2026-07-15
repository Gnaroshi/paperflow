# PaperFlow Product Design System

## 1. Product Character

PaperFlow is a local-first macOS operations tool for Zotero libraries. The UI
must feel calm, precise, and trustworthy. It is not a marketing dashboard and
must not use decoration where status, evidence, or safety information belongs.

Design priorities, in order:

1. Preserve user work and make destructive scope explicit.
2. Keep developer-only and decision-irrelevant information out of the default UI.
3. Show workflow order, prerequisites, and user-relevant results.
4. Keep every control usable from the minimum supported window size.
5. Make current state and next action obvious within three seconds.
6. Use color as a status signal, not as background decoration.

## 2. Layout Contract

### Main Window

- Supported minimum: 760 x 620 pt.
- Comfortable target: 1180 x 820 pt.
- Sidebar: 224 pt normally, 52 pt rail below 980 pt or when collapsed.
- Content gutter: 16 pt compact, 24 pt regular.
- Content width: fluid, capped at 1240 pt for reading-heavy screens.
- Command output: collapsed activity dock by default; expandable without
  permanently taking 160-260 pt from the main content.
- No view may require a width greater than its parent. Wide data tables must
  own their horizontal scroll view.

### Responsive Rules

- At widths below 900 pt, horizontal control groups stack vertically.
- At widths below 760 pt, the app relies on its minimum window constraint.
- Text fields use the available width and never declare an unconditional
  minimum wider than 220 pt.
- Button groups wrap with `FlowLayout`; they never clip off the trailing edge.
- Settings rows use label-over-control layout when horizontal space is tight.

## 3. Information Hierarchy

Every screen follows the same order:

1. **Screen header**: title, one-sentence purpose, optional top-level actions.
2. **Blocking notice**: missing prerequisite or safety warning, when present.
3. **Primary workflow**: numbered steps with state and required artifacts.
4. **Results**: counts, plans, tables, or review cards.
5. **Secondary detail**: logs, explanations, and advanced settings.

Avoid placing unrelated buttons in one undifferentiated grid. A button that
depends on another operation must display its prerequisite and disabled reason.

### User-facing information boundary

- Default screens show only purpose, prerequisite, blocker, progress, result,
  preservation and next action.
- Repository paths, executables, raw commands, PID, hashes, schema/API/backend
  terms, artifact filenames and raw logs are hidden by default.
- Those values are available only after enabling `Settings > Advanced &
  Diagnostics > Show technical details`, or through an explicit report/log action.
- Errors lead with a plain-language summary, what was preserved and how to recover.
  Raw output remains copyable in diagnostics.
- Safety, privacy, destructive scope and recovery instructions are never hidden as
  technical detail.

## 4. Surface System

- `canvas`: app background; a single restrained vertical gradient is allowed.
- `sidebar`: solid elevated surface.
- `surface`: primary content section.
- `surfaceRaised`: interactive or selected section.
- `surfaceInset`: logs, code, paths, and dense tables.
- One-pixel separators provide structure; cards do not float through shadows.
- Corner radius: 10 pt controls, 12 pt sections, 14 pt emphasized surfaces.
- No nested decorative cards. Use dividers and grouped rows inside a section.

## 5. Color Usage

Base surfaces occupy at least 85% of the interface. Accent colors occupy at
most 15% and have fixed semantics:

- sky: navigation selection and informational state.
- mint: completed, verified, and safe state.
- amber: attention, review, and stale output.
- rose: blocked, failed, or destructive state.
- lilac: active processing and optional AI assistance.

Gradients are limited to the app canvas and one compact accent strip in a hero
or active workflow. Text, cards, buttons, and section titles use solid colors.

## 6. Workflow State Model

Every ordered operation has one of these states:

- `blocked`: required input artifact is missing; action is disabled.
- `ready`: prerequisites exist; action can run.
- `running`: this exact command is active.
- `completed`: expected output artifact exists and is current.
- `outdated`: output exists but an input artifact is newer; rerun is required.

Dependent commands run as a success-gated sequence. Failure or cancellation of
one command prevents later commands in the same sequence from starting.

## 7. Safety Communication

- Dry-run and apply actions never share equal visual weight.
- Routine apply controls require a current preview and backup but do not require a
  repeated typed phrase. Irreversible cleanup keeps stronger confirmation.
- The UI states what changes and what is preserved.
- Missing credentials, missing plans, stale plans, and missing verification
  reports are blocking conditions, not transient toast messages.
- Errors remain visible in the main window until dismissed.

## 8. Accessibility and Legibility

- Body text targets 13-14 pt; captions are reserved for metadata.
- Primary text uses high contrast; muted text remains readable on every surface.
- Status is conveyed with icon, label, and color together.
- Interactive targets are at least 30 pt high.
- Paths and command output use monospaced text with truncation or scrolling.
- Labels never depend on hover-only tooltips for essential meaning.
- Technical detail is opt-in and off by default.

## 9. Review Checklist

Before shipping a screen:

- Resize to 760 x 620, 900 x 700, and 1180 x 820.
- Confirm no control or text is clipped on the trailing or bottom edge.
- Confirm the next valid workflow action is visible.
- Confirm blocked actions explain the missing prerequisite.
- Confirm a failed sequence cannot execute its remaining steps.
- Confirm gradients are limited to the canvas or active accent.
- Confirm destructive actions remain separated and explicitly confirmed.

## 10. Settings Form Contract

PaperFlow settings follow the durable layout rules in `gnaroshi_mds`: spacing
tokens replace arbitrary gaps, controls are grouped by role, and narrow layouts
reflow rather than clip.

- A setting row has one label/detail column and one control column.
- Regular layout uses a 200 pt label column, 24 pt gutter, and 380 pt control
  column. All picker, text field, slider, and stepper controls share this axis.
- Boolean settings use a trailing macOS switch in the control column. A raw
  labelled checkbox must not float between field rows.
- Dependent controls appear directly below their parent toggle and remain hidden
  while the feature is disabled.
- Commands and preview buttons live in a separated action bar; they are not mixed
  into the form row grid.
- Every row can include a short consequence-oriented detail. Repeated prose below
  unrelated controls is not allowed.
- Below the horizontal fit threshold, each row becomes label-over-control while
  preserving the same semantic order and full-width control.
- Section spacing uses `PaperFlowSpacing`; local numeric spacing is reserved for
  intrinsic control sizing only.

## 11. Storage Location Contract

PaperFlow distinguishes destinations from sources. A filesystem folder must not be
called a vault merely because it contains PDFs.

- `PaperFlow Managed Vault` is the single default write destination for new linked
  PDFs. It corresponds to Zotero's one Linked Attachment Base Directory.
- `Existing Zotero Storage` is a Zotero-managed, read-only source. PaperFlow never
  writes into `Zotero/storage` directly and only migrates stored attachments through
  the Plan -> Apply -> Verify localization workflow.
- `Import Sources` such as Downloads are temporary scan roots. Dry-run scanning does
  not copy files or write Zotero data.
- Applying an import copies the PDF to the managed vault and creates or updates the
  Zotero parent item, collections, tags, and linked-file attachment.
- Every CLI plan receives the selected managed vault path explicitly; UI path changes
  must not silently fall back to the backend default.
