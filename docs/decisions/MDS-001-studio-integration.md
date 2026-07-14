# MDS-001: Gnaroshi Studio integration

- Status: accepted
- Date: 2026-07-12
- PaperFlow baseline: `056e6251dc07cc74f39c1df7ed2060481e623083`
- Integration schema: 1
- Provider ID: `paperflow`

## Context

PaperFlow remains the independently runnable owner of Zotero library operations and its managed linked-PDF vault. Gnaroshi Studio is a control plane for discovery, availability, launch, read-only status, dry-run preview, and reviewed handoff. Studio is not a Zotero client, PaperFlow storage owner, or alternate apply surface.

The active local PaperFlow checkout contained substantial unrelated SwiftUI and ingest work before this change. Integration development used a clean linked worktree from the recorded baseline and did not modify or stage that work.

## Preserved functionality

### CLI inventory

The pre-integration command surface remains available:

- root: `ingest`, `zotero`, `vault`, `local`, `credentials`, `cleanup`, `taxonomy`;
- Zotero: scan, organization plan/report, disabled legacy apply preview, backup, metadata enrichment, duplicate detection, migration plan/dry-run/apply, collection cleanup, attachment localization/apply/verify/cleanup, explain, audit, and rollback;
- local import: scan, Zotero index/match, classify, plan, apply, audit, and source quarantine;
- cleanup: abstract/metadata repair and duplicate planning;
- taxonomy: explain, golden-set maintenance, and evaluation;
- vault and credential verification workflows.

Schema-v1 integration adds `version`, `status`, `doctor`, and preview-only `import`. Existing commands retain their human-readable output when `--json` is absent.

### Native SwiftUI/AppKit flows

The native app keeps Dashboard, Drop Shelf Settings, Zotero Organize, Local Vault, Local Folder Import, Existing Attachments, Cleanup Workbench, User Guide, Reports, Settings, and Logs. Swift continues to invoke the Python CLI rather than duplicating Zotero domain logic.

The AppKit menu bar, command popup, floating drop shelf, global shortcuts, multi-monitor placement, Keychain use, command activity, and main-window workflow remain unchanged. Existing apply operations still require their operation-specific confirmation phrase.

### Existing output formats

| Workflow | Preserved output |
| --- | --- |
| Zotero scan | `data/zotero_items.jsonl`, `data/zotero_items.csv` |
| Organization plan | `data/organize_plan.json` |
| Organization report | `data/organize_report.md`, `data/organize_report.csv` |
| Ingest preview | `data/ingest_plan.json`, `data/ingest_report.md` |
| Ingest progress | JSON Lines when `--progress-jsonl` is selected |
| Migration, cleanup, localization, audit, rollback | existing JSON/Markdown plans, previews, reports, backup manifests, and apply logs |

The Studio JSON envelope is an additional stdout contract. It does not replace or silently reinterpret these artifacts.

### Zotero and filesystem safety guarantees

- Never edit `zotero.sqlite`.
- Zotero Local API operations are GET-only and read-only.
- Never rename a source PDF automatically.
- Never delete automatically.
- Never upload PDF bytes to Zotero Storage by default.
- Planning and Studio handoff are dry-run only.
- Every existing write remains behind its explicit `--apply`, prerequisite checks, scope preview, and exact confirmation.
- Studio cannot invoke migration apply, cleanup, localization apply, rollback, or source cleanup.
- Parent items, notes, annotations, highlights, child notes, reading activity, and stored attachments retain their existing protection rules.
- Credentials remain in Keychain/environment and are never placed in the manifest, stdout data, paths, logs, or Studio configuration.

## MDS changes applied

- Provider-owned `gnaroshi.app.json` with real bundle ID, application name/version, CLI entrypoint, fixed version/status/health commands, capabilities, data owner, privacy, and compatibility version.
- Common schema-v1 JSON envelope containing provider/contract version, capability, generated time, explicit status, data, warnings, and stable errors.
- `paperflow status --json`, `doctor --json`, `zotero scan --json`, and `zotero plan-organize --json`.
- Preview-only handoff for user-selected PDF, paper URL, arXiv ID, or validated metadata candidate.
- Allowlisted handoff dispositions: `accepted`, `duplicate`, `needs-review`, and `rejected`.
- Stable opaque source IDs, read-only duplicate detection, explicit planned changes, and resulting Zotero record ID only when a duplicate is observed.
- Non-zero error exits, one JSON value on stdout, generic diagnostics on stderr, and no private path or candidate content in response summaries.
- Explicit current state, prerequisite, blocker, and next action for Studio cards without changing PaperFlow’s native visual architecture.

## Intentional deviations

- No `paperflow://` scheme is added. The current native app has navigation and drop-state APIs, but it does not yet have a versioned external routing/prefill contract with dedicated URL tests. Studio uses bundle-ID launch and typed CLI preview instead. This avoids introducing an untested path that could accidentally advance an import.
- No local HTTP endpoint or background daemon is added; fixed CLI commands are sufficient.
- No new apply action is exposed. Write integration requires a separate decision after provider-owned confirmation and recovery can be proven end to end.
- No broad UI rewrite is made. The existing dark, responsive, pastel-accented design and stronger five-state workflow remain authoritative.

## Contract behavior

```text
Studio selected source
        |
paperflow import --<one source> --dry-run --json
        |
validate source -> optional Local API duplicate scan -> planned changes
        |
accepted | duplicate | needs-review | rejected
        |
open PaperFlow for user review
```

For a PDF, PaperFlow may plan a copy into the managed vault and a linked-local Zotero attachment. It never renames or removes the source. URL, arXiv, and metadata inputs remain `needs-review` until PaperFlow has a user-selected PDF or observes a duplicate. No handoff writes a local record; `resultingLocalRecordId` is returned only for an observed existing Zotero item.

## Compatibility and migration

- Manifest schema 1 and integration contract 1 require Studio `>=0.1.0`.
- CLI provider and native bundle version are `0.2.0`. Version JSON and the app bundle also carry Git commit/build provenance; the release tag must match the semantic version.
- Provider adoption is additive. PaperFlow remains usable without Studio, and Studio degrades when PaperFlow is missing, blocked, malformed, timed out, or incompatible.
- Merge the PaperFlow provider contract before enabling the Studio adapter in a release. Mixed versions must show setup/incompatible rather than infer availability.
- No data migration, backfill, database change, or shared state is introduced.

## Tests

- Baseline fixture: CLI inventory, native sections, confirmations, output artifacts, bundle ID, and safety promises.
- JSON contract: manifest values, version/status, health success/blocker, Local API scan, organization planning, redacted errors, non-zero exits, and unchanged human output.
- Handoff: all four source types; accepted, duplicate, needs-review, rejected; exact-one input; dry-run requirement; invalid source; path/content redaction; no executed planned change.
- Full Python suite: 122 tests pass.
- Python bytecode compilation passes.
- Swift package builds successfully. The baseline has no Swift test target, so `swift test` builds and then reports `no tests found`; no Swift source changes are made by this integration.

## Rollback

1. Disable or revert the Studio PaperFlow adapter.
2. Revert the PaperFlow documentation, handoff, contract, and baseline commits in reverse order.
3. Rebuild the Python package and native app if distributed.
4. Do not delete or alter Zotero, the managed vault, backup manifests, reports, or app preferences; the integration created none of them.

## Related changes

PaperFlow commits:

- `e8952db` — baseline regression fixture
- `e07914d` — machine-readable provider contract
- `28efc49` — preview-only handoff
- documentation commit containing this decision

The linked Studio commit and both PR URLs are recorded in the pull-request descriptions after creation. Provider PR must merge before or alongside the Studio consumer; Studio remains degraded until it can validate the provider.
