import SwiftUI

enum PaperFlowTheme {
    static let canvas0 = Color(red: 0.035, green: 0.040, blue: 0.070)
    static let canvas1 = Color(red: 0.060, green: 0.070, blue: 0.115)
    static let panel0 = Color(red: 0.082, green: 0.092, blue: 0.145)
    static let panel1 = Color(red: 0.115, green: 0.120, blue: 0.185)
    static let panel2 = Color(red: 0.155, green: 0.145, blue: 0.215)
    static let ink = Color(red: 0.945, green: 0.960, blue: 0.980)
    static let muted = Color(red: 0.660, green: 0.705, blue: 0.780)
    static let faint = Color(red: 0.430, green: 0.470, blue: 0.570)
    static let mint = Color(red: 0.425, green: 0.965, blue: 0.800)
    static let sky = Color(red: 0.420, green: 0.760, blue: 1.000)
    static let lilac = Color(red: 0.760, green: 0.610, blue: 1.000)
    static let rose = Color(red: 1.000, green: 0.500, blue: 0.680)
    static let amber = Color(red: 1.000, green: 0.780, blue: 0.420)
    static let line = Color(red: 0.310, green: 0.365, blue: 0.475).opacity(0.42)

    static func panelGradient(tint: Color = PaperFlowTheme.sky.opacity(0.12)) -> LinearGradient {
        LinearGradient(
            colors: [
                panel1,
                panel0,
                tint.opacity(0.26)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}

struct PaperFlowAuroraBackground: View {
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [PaperFlowTheme.canvas0, PaperFlowTheme.canvas1, PaperFlowTheme.canvas0],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            RadialGradient(
                colors: [PaperFlowTheme.sky.opacity(0.34), .clear],
                center: .topLeading,
                startRadius: 18,
                endRadius: 620
            )
            RadialGradient(
                colors: [PaperFlowTheme.lilac.opacity(0.28), .clear],
                center: .bottomTrailing,
                startRadius: 24,
                endRadius: 580
            )
            RadialGradient(
                colors: [PaperFlowTheme.mint.opacity(0.18), .clear],
                center: .bottomLeading,
                startRadius: 30,
                endRadius: 520
            )
        }
    }
}

struct PaperFlowCardModifier: ViewModifier {
    var tint: Color = PaperFlowTheme.sky
    var radius: CGFloat = 16
    var emphasize: Bool = false

    func body(content: Content) -> some View {
        content
            .background(
                ZStack {
                    PaperFlowTheme.panelGradient(tint: tint)
                    tint.opacity(emphasize ? 0.12 : 0.055)
                }
            )
            .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .stroke(PaperFlowTheme.line.opacity(emphasize ? 0.82 : 0.58), lineWidth: 1)
            )
            .shadow(color: tint.opacity(emphasize ? 0.18 : 0.08), radius: emphasize ? 22 : 12, x: 0, y: emphasize ? 12 : 7)
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
