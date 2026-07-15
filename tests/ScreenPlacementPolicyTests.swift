import AppKit

@main
enum ScreenPlacementPolicyTests {
    static func main() {
        testSpacesDefaultMigration()
        testSpacesOptOutSurvivesCompletedMigration()
        print("ScreenPlacementPolicyTests passed")
    }

    private static func testSpacesDefaultMigration() {
        let migratedValue = ScreenPlacementPolicy.showAcrossSpacesValue(
            currentValue: false,
            migrationApplied: false
        )

        precondition(migratedValue, "An existing current-Space-only default must migrate to all Spaces")
    }

    private static func testSpacesOptOutSurvivesCompletedMigration() {
        let preservedValue = ScreenPlacementPolicy.showAcrossSpacesValue(
            currentValue: false,
            migrationApplied: true
        )

        precondition(!preservedValue, "A later explicit opt-out must remain disabled")
    }
}
