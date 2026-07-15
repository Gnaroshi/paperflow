import SwiftUI

enum PaperFlowTheme {
    static let canvas0 = Color(red: 0.034, green: 0.039, blue: 0.061)
    static let canvas1 = Color(red: 0.050, green: 0.057, blue: 0.086)
    static let sidebar = Color(red: 0.045, green: 0.051, blue: 0.076)
    static let panel0 = Color(red: 0.064, green: 0.072, blue: 0.105)
    static let panel1 = Color(red: 0.082, green: 0.091, blue: 0.130)
    static let panel2 = Color(red: 0.105, green: 0.114, blue: 0.157)
    static let ink = Color(red: 0.948, green: 0.958, blue: 0.978)
    static let muted = Color(red: 0.705, green: 0.735, blue: 0.795)
    static let faint = Color(red: 0.485, green: 0.520, blue: 0.605)
    static let mint = Color(red: 0.455, green: 0.900, blue: 0.735)
    static let sky = Color(red: 0.455, green: 0.710, blue: 0.960)
    static let lilac = Color(red: 0.715, green: 0.625, blue: 0.935)
    static let rose = Color(red: 0.945, green: 0.475, blue: 0.615)
    static let amber = Color(red: 0.945, green: 0.710, blue: 0.365)
    static let line = Color(red: 0.275, green: 0.305, blue: 0.390).opacity(0.56)

    static func panelGradient(tint: Color = PaperFlowTheme.sky) -> LinearGradient {
        LinearGradient(
            colors: [panel1, tint.opacity(0.20)],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}

enum PaperFlowSpacing {
    static let xxs: CGFloat = 4
    static let xs: CGFloat = 8
    static let sm: CGFloat = 12
    static let md: CGFloat = 16
    static let lg: CGFloat = 24
    static let xl: CGFloat = 32
}

enum SettingsMetrics {
    static let labelWidth: CGFloat = 200
    static let controlWidth: CGFloat = 380
    static let rowMinHeight: CGFloat = 36
}

struct PaperFlowAuroraBackground: View {
    var body: some View {
        LinearGradient(
            colors: [PaperFlowTheme.canvas1, PaperFlowTheme.canvas0],
            startPoint: .top,
            endPoint: .bottom
        )
    }
}

struct PaperFlowCardModifier: ViewModifier {
    var tint: Color = PaperFlowTheme.sky
    var radius: CGFloat = 16
    var emphasize: Bool = false

    func body(content: Content) -> some View {
        content
            .background(
                PaperFlowTheme.panel1
            )
            .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .stroke(emphasize ? tint.opacity(0.58) : PaperFlowTheme.line, lineWidth: 1)
            )
            .shadow(color: .black.opacity(emphasize ? 0.20 : 0.10), radius: emphasize ? 14 : 6, x: 0, y: emphasize ? 8 : 3)
    }
}

struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) -> CGSize {
        let width = proposal.width ?? 0
        var currentX: CGFloat = 0
        var currentY: CGFloat = 0
        var lineHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if currentX > 0, currentX + size.width > width {
                currentX = 0
                currentY += lineHeight + spacing
                lineHeight = 0
            }
            currentX += size.width + spacing
            lineHeight = max(lineHeight, size.height)
        }
        return CGSize(width: width, height: currentY + lineHeight)
    }

    func placeSubviews(
        in bounds: CGRect,
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) {
        var currentX = bounds.minX
        var currentY = bounds.minY
        var lineHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if currentX > bounds.minX, currentX + size.width > bounds.maxX {
                currentX = bounds.minX
                currentY += lineHeight + spacing
                lineHeight = 0
            }
            subview.place(
                at: CGPoint(x: currentX, y: currentY),
                anchor: .topLeading,
                proposal: ProposedViewSize(size)
            )
            currentX += size.width + spacing
            lineHeight = max(lineHeight, size.height)
        }
    }
}

struct ResponsiveSettingRow<Content: View>: View {
    let label: String
    let detail: String?
    let content: Content

    init(_ label: String, detail: String? = nil, @ViewBuilder content: () -> Content) {
        self.label = label
        self.detail = detail
        self.content = content()
    }

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .center, spacing: PaperFlowSpacing.lg) {
                settingLabel
                    .frame(width: SettingsMetrics.labelWidth, alignment: .leading)
                content
                    .frame(width: SettingsMetrics.controlWidth, alignment: .leading)
            }
            .frame(maxWidth: .infinity, minHeight: SettingsMetrics.rowMinHeight, alignment: .leading)

            VStack(alignment: .leading, spacing: PaperFlowSpacing.xs) {
                settingLabel
                content
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxWidth: .infinity, minHeight: SettingsMetrics.rowMinHeight, alignment: .leading)
        }
        .padding(.vertical, PaperFlowSpacing.xxs)
    }

    private var settingLabel: some View {
        VStack(alignment: .leading, spacing: PaperFlowSpacing.xxs) {
            Text(label)
                .font(.callout.weight(.medium))
            if let detail, !detail.isEmpty {
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(PaperFlowTheme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

struct SettingsToggleRow: View {
    let label: String
    let detail: String?
    let isOn: Binding<Bool>

    init(_ label: String, detail: String? = nil, isOn: Binding<Bool>) {
        self.label = label
        self.detail = detail
        self.isOn = isOn
    }

    var body: some View {
        ResponsiveSettingRow(label, detail: detail) {
            Toggle(label, isOn: isOn)
                .labelsHidden()
                .toggleStyle(.switch)
                .frame(maxWidth: .infinity, alignment: .trailing)
                .accessibilityLabel(label)
        }
    }
}

struct SettingsActionBar<Content: View>: View {
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: PaperFlowSpacing.sm) {
            Rectangle()
                .fill(PaperFlowTheme.line)
                .frame(height: 1)
            FlowLayout(spacing: PaperFlowSpacing.xs) {
                content
            }
        }
        .padding(.top, PaperFlowSpacing.xxs)
    }
}

struct SettingsSubsectionHeader: View {
    let title: String
    let detail: String?

    init(_ title: String, detail: String? = nil) {
        self.title = title
        self.detail = detail
    }

    var body: some View {
        VStack(alignment: .leading, spacing: PaperFlowSpacing.xxs) {
            Text(title)
                .font(.subheadline.weight(.semibold))
            if let detail {
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(PaperFlowTheme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

extension View {
    func paperFlowCard(tint: Color = PaperFlowTheme.sky, radius: CGFloat = 16, emphasize: Bool = false) -> some View {
        modifier(PaperFlowCardModifier(tint: tint, radius: radius, emphasize: emphasize))
    }

    func paperFlowTextInput(radius: CGFloat = 10) -> some View {
        textFieldStyle(.plain)
            .padding(.vertical, 7)
            .padding(.horizontal, 10)
            .background(PaperFlowTheme.panel0.opacity(0.94))
            .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .stroke(PaperFlowTheme.line, lineWidth: 1)
            )
    }
}
