import SwiftUI

struct UserGuideView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionTitle("사용 가이드")

            guideCard(
                title: "1. PaperFlow의 기본 원칙",
                icon: "lock.shield",
                text: """
                PaperFlow는 Zotero 논문과 PDF를 안전하게 정리합니다. PDF는 기본적으로 이 Mac에 보관하며, Apply 전에 항상 변경 내용을 미리 확인할 수 있습니다.
                """
            )

            guideCard(
                title: "2. Floating Window 열기",
                icon: "tray.and.arrow.up",
                text: """
                Floating Window는 Settings에서 선택한 단축키로 열고 닫습니다. 기본값은 ⌃⇧⌘+이며, Desktop을 전환해도 함께 이동합니다.
                """
            )

            guideCard(
                title: "3. 로컬 폴더 가져오기",
                icon: "folder.badge.plus",
                text: """
                Local Folder Import에서 폴더를 선택한 뒤 화면에 표시된 순서대로 Scan → Match → Classify → Preview를 실행합니다. 중복 가능성이 있거나 분류가 불확실한 논문은 바로 추가하지 않고 Review Queue로 보냅니다.
                """
            )

            guideCard(
                title: "4. Review Queue와 분류 수정",
                icon: "slider.horizontal.3",
                text: """
                보류된 결과 카드에는 이유와 다음 행동이 표시됩니다. Zotero에서 제목과 초록을 확인하고 가장 구체적인 collection을 선택하세요. Correct classification에서 수정한 뒤 Save as Rule을 누르면 같은 유형의 논문에도 재사용됩니다.
                """
            )

            guideCard(
                title: "5. Zotero 정리",
                icon: "books.vertical",
                text: """
                Zotero Organize는 Backup → 서지정보 확인 → 중복 확인 → Plan → Preview → Apply 순서로 사용합니다. 현재 backup과 preview가 준비되면 Apply를 한 번 눌러 실행할 수 있으며, 메모와 읽기 기록은 보존됩니다.
                """
            )

            guideCard(
                title: "6. 기술 세부정보가 필요한 경우",
                icon: "wrench.and.screwdriver",
                text: """
                일반 사용에는 경로, 명령, 로그가 필요하지 않습니다. 문제를 직접 확인해야 할 때만 Settings → Advanced & Diagnostics에서 Show technical details를 켜세요.
                """
            )
        }
        .frame(maxWidth: 920, alignment: .leading)
    }

    private func guideCard(title: String, icon: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(PaperFlowTheme.mint)
                .frame(width: 28)
            VStack(alignment: .leading, spacing: 6) {
                Text(title)
                    .font(.headline)
                Text(text)
                    .font(.callout)
                    .foregroundStyle(PaperFlowTheme.muted)
                    .lineSpacing(2)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .paperFlowCard(tint: PaperFlowTheme.lilac, radius: 16)
    }
}
