import SwiftUI

struct ShowcaseView: View {
    enum Step: String, CaseIterable { case scan = "Scan summary", plan = "Plan review", apply = "Apply boundary" }
    @State private var step: Step

    init() { _step = State(initialValue: Step(rawValue: ProcessInfo.processInfo.environment["GNAROSHI_SHOWCASE_STEP"] ?? "") ?? .plan) }

    var body: some View {
        NavigationSplitView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 3) { Text("PaperFlow").font(.headline); Text("Example library").foregroundStyle(.secondary) }
                ForEach(Step.allCases, id: \.self) { item in Button { step = item } label: { Label(item.rawValue, systemImage: icon(item)).frame(maxWidth: .infinity, alignment: .leading).padding(9).background(step == item ? Color.accentColor.opacity(0.14) : .clear).clipShape(RoundedRectangle(cornerRadius: 5)) }.buttonStyle(.plain) }
                Spacer()
                Text("Example data\nRead-only Zotero fixture\nNo real library is opened").font(.caption).foregroundStyle(.secondary).padding(12).overlay(RoundedRectangle(cornerRadius: 5).stroke(.quaternary))
            }.padding(18).navigationSplitViewColumnWidth(min: 210, ideal: 230)
        } detail: {
            ScrollView { VStack(alignment: .leading, spacing: 22) {
                Text("Zotero organization").font(.caption.bold()).foregroundStyle(.tint)
                Text(step.rawValue).font(.system(size: 30, weight: .bold))
                Text(subtitle).foregroundStyle(.secondary)
                switch step {
                case .scan: scanView
                case .plan: planView
                case .apply: applyView
                }
            }.frame(maxWidth: 860, alignment: .leading).padding(42) }
        }.preferredColorScheme(ProcessInfo.processInfo.environment["GNAROSHI_SHOWCASE_THEME"] == "light" ? .light : .dark)
    }

    private var scanView: some View { HStack(spacing: 12) { metric("126", "Library items"); metric("18", "Proposed moves"); metric("3", "Duplicate groups"); metric("0", "Writes") } }
    private var planView: some View { VStack(spacing: 10) { proposal("Create collection", "Example / Vision-Language Action", "12 papers"); proposal("Move candidates", "Unsorted → Example / Systems", "6 papers"); proposal("Review duplicates", "3 groups require owner choice", "No deletion") }.overlay(alignment: .bottomTrailing) { Button("Continue to apply boundary") { step = .apply }.buttonStyle(.borderedProminent).padding(.top, 16).offset(y: 54) }.padding(.bottom, 54) }
    private var applyView: some View { VStack(alignment: .leading, spacing: 16) { Label("Explicit apply required", systemImage: "hand.raised.fill").font(.title2.bold()).foregroundStyle(.orange); Text("This showcase stops before any Zotero write. The normal application requires a current preview and an explicit Apply action."); HStack { Button("Back to plan") { step = .plan }; Button("Apply changes") {}.disabled(true) } }.padding(24).background(Color.orange.opacity(0.09)).clipShape(RoundedRectangle(cornerRadius: 7)) }
    private var subtitle: String { switch step { case .scan: "A deterministic synthetic library is scanned without a Zotero process or credential."; case .plan: "Review collection and duplicate proposals before any write-capable action."; case .apply: "The safety boundary is visible and disabled in showcase mode." } }
    private func icon(_ item: Step) -> String { switch item { case .scan: "doc.text.magnifyingglass"; case .plan: "list.bullet.rectangle"; case .apply: "hand.raised" } }
    private func metric(_ value: String, _ label: String) -> some View { VStack(alignment: .leading) { Text(value).font(.title.bold()); Text(label).foregroundStyle(.secondary) }.frame(maxWidth: .infinity, alignment: .leading).padding(18).background(Color(nsColor: .controlBackgroundColor)).clipShape(RoundedRectangle(cornerRadius: 6)) }
    private func proposal(_ action: String, _ detail: String, _ scope: String) -> some View { HStack { Image(systemName: "arrow.right.circle").foregroundStyle(.tint); VStack(alignment: .leading) { Text(action).font(.headline); Text(detail).foregroundStyle(.secondary) }; Spacer(); Text(scope).font(.caption.bold()) }.padding(18).background(Color(nsColor: .controlBackgroundColor)).clipShape(RoundedRectangle(cornerRadius: 6)) }
}
