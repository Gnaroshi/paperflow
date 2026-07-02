import SwiftUI

struct UserGuideView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionTitle("사용 가이드")

            guideCard(
                title: "1. PaperFlow의 기본 원칙",
                icon: "lock.shield",
                text: """
                PaperFlow는 로컬 우선 Zotero 논문 관리 앱입니다. PDF는 기본적으로 로컬 vault에 보관하고, Zotero에는 metadata, collection, tag, note, annotation, linked attachment만 유지합니다. Zotero Storage에 PDF를 업로드하지 않는 것이 기본 정책입니다.
                """
            )

            guideCard(
                title: "2. Floating Window 열기",
                icon: "tray.and.arrow.up",
                text: """
                PFW는 기본적으로 숨겨져 있습니다. Settings에서 선택한 단축키로 열고 닫습니다. 기본값은 ⌃⇧⌘+ 입니다. 메뉴바의 Shelf 버튼이나 메인 창 상단 Shelf 버튼도 같은 toggle 동작을 합니다.
                """
            )

            guideCard(
                title: "3. 로컬 폴더 가져오기",
                icon: "folder.badge.plus",
                text: """
                Local Folder Import에서 폴더를 선택한 뒤 Scan Folder → Match Zotero → Classify New Papers → Plan Import 순서로 실행합니다. Strong/likely duplicate는 기본 import에서 제외되고, possible duplicate/update candidate는 Review Queue로 갑니다.
                """
            )

            guideCard(
                title: "4. 분류 수정",
                icon: "slider.horizontal.3",
                text: """
                Local Folder Import 테이블에서 Correct classification을 누르면 collection/tag를 고칠 수 있습니다. Save as Rule을 누르면 config/user_taxonomy_overrides.yaml에 사용자 규칙으로 저장되고, pending queue가 다시 분류됩니다.
                """
            )

            guideCard(
                title: "5. Zotero 정리",
                icon: "books.vertical",
                text: """
                Zotero Organize는 Backup → Enrich Metadata → Detect Duplicates → Plan Migration → Dry Run Migration → Apply Migration 순서로 사용합니다. Apply는 반드시 REPLACE MY ZOTERO COLLECTIONS 입력이 필요하며, notes/highlights/annotations/attachments를 삭제하지 않아야 합니다.
                """
            )

            guideCard(
                title: "6. Golden Set 검증",
                icon: "checkmark.seal",
                text: """
                분류기가 랜덤하게 변하지 않도록 data/golden_classifications.yaml을 사용합니다. CLI에서 uv run paperflow taxonomy evaluate를 실행하면 regression count를 확인할 수 있습니다. 새 기준 논문은 taxonomy add-golden으로 추가합니다.
                """
            )
        }
        .frame(maxWidth: 920, alignment: .leading)
    }

    private func guideCard(title: String, icon: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(Color(red: 0.36, green: 0.40, blue: 0.86))
                .frame(width: 28)
            VStack(alignment: .leading, spacing: 6) {
                Text(title)
                    .font(.headline)
                Text(text)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .lineSpacing(2)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            LinearGradient(
                colors: [
                    Color(red: 0.96, green: 0.97, blue: 1.0),
                    Color(red: 1.0, green: 0.96, blue: 0.98)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .shadow(color: Color.black.opacity(0.05), radius: 10, x: 0, y: 5)
    }
}
