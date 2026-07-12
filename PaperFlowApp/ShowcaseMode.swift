import Foundation

enum ShowcaseMode {
    static func isEnabled(environment: [String: String] = ProcessInfo.processInfo.environment, arguments: [String] = CommandLine.arguments) -> Bool {
        environment["GNAROSHI_SHOWCASE"] == "1" || arguments.contains("--showcase")
    }
}
