# PaperFlow showcase

Set `GNAROSHI_SHOWCASE=1` or pass `--showcase`. The dedicated SwiftUI view uses a deterministic synthetic library, performs no Zotero request, reads no credential, and exposes no enabled apply action. Normal execution keeps `MainWindowView` and all existing dry-run/apply safeguards.

`GNAROSHI_SHOWCASE_STEP` selects `Scan summary`, `Plan review`, or `Apply boundary`; `GNAROSHI_SHOWCASE_THEME=light` performs light-mode verification. Run `cd PaperFlowApp && sh Tests/check-showcase.sh && swift build` to verify the boundary.
