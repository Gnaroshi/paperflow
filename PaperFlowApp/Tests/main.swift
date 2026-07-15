import Foundation

precondition(!ShowcaseMode.isEnabled(environment: [:], arguments: ["PaperFlowApp"]))
precondition(ShowcaseMode.isEnabled(environment: ["GNAROSHI_SHOWCASE": "1"], arguments: ["PaperFlowApp"]))
precondition(ShowcaseMode.isEnabled(environment: [:], arguments: ["PaperFlowApp", "--showcase"]))
print("PaperFlow showcase boundary verified")
