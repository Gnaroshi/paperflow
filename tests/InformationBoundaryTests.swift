import Foundation

@main
enum InformationBoundaryTests {
    static func main() {
        let defaultSections = AppSection.visibleCases(showTechnicalDetails: false)
        precondition(!defaultSections.contains(.logs), "Logs must stay hidden in the default navigation")
        precondition(
            AppSection.visibleCases(showTechnicalDetails: true).contains(.logs),
            "Advanced diagnostics must make Logs discoverable"
        )

        let defaultPFWModes = PFWMode.visibleCases(showTechnicalDetails: false)
        precondition(!defaultPFWModes.contains(.logs), "PFW Logs must stay hidden by default")
        precondition(
            PFWMode.visibleCases(showTechnicalDetails: true).contains(.logs),
            "Advanced diagnostics must make PFW Logs discoverable"
        )

        print("InformationBoundaryTests passed")
    }
}
