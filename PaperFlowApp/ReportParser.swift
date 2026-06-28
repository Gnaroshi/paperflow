import Foundation

struct ReportNumbers {
    var sourceItems = 0
    var plannedItems = 0
    var duplicateCandidates = 0
    var missingMetadata = 0
    var missingAbstracts = 0
    var itemUpdates = 0
    var collectionsToCreate = 0
    var oldCollectionsWouldBeEmpty = 0
}

enum ReportParser {
    static func numbers(dataURL: URL) -> ReportNumbers {
        var numbers = ReportNumbers()
        if let migration = readJSON(dataURL.appendingPathComponent("migration_plan.json")),
           let stats = migration["stats"] as? [String: Any] {
            numbers.sourceItems = stats["source_items"] as? Int ?? 0
            numbers.plannedItems = stats["planned_items"] as? Int ?? 0
            numbers.duplicateCandidates = stats["duplicate_candidates"] as? Int ?? 0
            numbers.missingMetadata = stats["missing_metadata"] as? Int ?? 0
            numbers.missingAbstracts = stats["missing_abstract"] as? Int ?? 0
        }

        if let preview = readJSON(dataURL.appendingPathComponent("apply_preview.json")) {
            numbers.itemUpdates = (preview["item_updates"] as? [[String: Any]])?.count ?? 0
            numbers.collectionsToCreate = (preview["collections_to_create"] as? [[String: Any]])?.count ?? 0
            numbers.oldCollectionsWouldBeEmpty = (preview["old_collections_that_would_be_empty"] as? [[String: Any]])?.count ?? 0
        }

        if numbers.duplicateCandidates == 0,
           let dedupe = readJSON(dataURL.appendingPathComponent("dedupe_plan.json")),
           let groups = dedupe["groups"] as? [[String: Any]] {
            numbers.duplicateCandidates = groups.reduce(0) { count, group in
                let items = group["items"] as? [[String: Any]] ?? []
                return count + items.filter { !($0["is_canonical"] as? Bool ?? false) }.count
            }
        }
        return numbers
    }

    static func cleanupWorkbenchData(dataURL: URL) -> CleanupWorkbenchData {
        guard let migration = readJSON(dataURL.appendingPathComponent("migration_plan.json")),
              let migrationItems = migration["items"] as? [[String: Any]] else {
            return CleanupWorkbenchData()
        }

        let enrichedItems = readJSONL(dataURL.appendingPathComponent("zotero_items_enriched.jsonl"))
        let enrichedByKey = Dictionary(uniqueKeysWithValues: enrichedItems.compactMap { row in
            string(row["key"]).map { ($0, row) }
        })
        let abstractRepairs = repairRows(
            dataURL.appendingPathComponent("abstract_repair_plan.json"),
            keyName: "item_key"
        )
        let metadataRepairs = repairRows(
            dataURL.appendingPathComponent("metadata_repair_plan.json"),
            keyName: "item_key"
        )

        var data = CleanupWorkbenchData()
        var rowsByKey: [String: CleanupWorkbenchItem] = [:]

        for migrationItem in migrationItems {
            guard let key = string(migrationItem["item_key"]) else {
                continue
            }
            let enriched = enrichedByKey[key] ?? [:]
            let row = workbenchItem(
                migrationItem: migrationItem,
                enrichedItem: enriched,
                abstractRepair: abstractRepairs[key],
                metadataRepair: metadataRepairs[key]
            )
            rowsByKey[key] = row
            data.allItems.append(row)

            if row.plannedCollections.contains("AI Library/40 Cleanup/Missing Abstract")
                || row.normalizedTags.contains("cleanup/missing-abstract") {
                data.missingAbstract.append(row)
            }
            if row.plannedCollections.contains("AI Library/40 Cleanup/Missing Metadata")
                || row.normalizedTags.contains("cleanup/missing-metadata") {
                data.missingMetadata.append(row)
            }
            if row.plannedCollections.contains("AI Library/40 Cleanup/Non-Paper Items")
                || row.normalizedTags.contains("cleanup/non-paper") {
                data.nonPaper.append(row)
            }
            if row.confidence < 0.55 {
                data.lowConfidence.append(row)
            }
        }

        data.duplicateGroups = duplicateGroups(
            dataURL: dataURL,
            migrationItems: migrationItems,
            enrichedByKey: enrichedByKey,
            rowsByKey: rowsByKey
        )
        return data
    }

    static func explainItems(dataURL: URL, query: String) -> [CleanupWorkbenchItem] {
        let all = cleanupWorkbenchData(dataURL: dataURL)
        let dedupeRows = Set(all.duplicateGroups.flatMap(\.items).map(\.itemKey))
        let expandedRows = all.allItems.sorted { $0.title < $1.title }
        let lowered = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !lowered.isEmpty else {
            return expandedRows
        }
        return expandedRows.filter { row in
            row.itemKey.lowercased().contains(lowered)
                || row.title.lowercased().contains(lowered)
                || row.doi.lowercased().contains(lowered)
                || row.arxivID.lowercased().contains(lowered)
                || dedupeRows.contains(row.itemKey)
        }
    }

    static func latestApplyLog(dataURL: URL) -> URL? {
        latestFile(dataURL: dataURL, prefix: "apply_log_", suffix: ".md")
    }

    static func latestFile(dataURL: URL, prefix: String, suffix: String) -> URL? {
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: dataURL,
            includingPropertiesForKeys: [.contentModificationDateKey]
        ) else {
            return nil
        }
        return files
            .filter { $0.lastPathComponent.hasPrefix(prefix) && $0.lastPathComponent.hasSuffix(suffix) }
            .max { modificationDate($0) < modificationDate($1) }
    }

    static func readJSON(_ url: URL) -> [String: Any]? {
        guard let data = try? Data(contentsOf: url),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        return object
    }

    private static func workbenchItem(
        migrationItem: [String: Any],
        enrichedItem: [String: Any],
        abstractRepair: [String: Any]?,
        metadataRepair: [String: Any]?
    ) -> CleanupWorkbenchItem {
        let key = string(migrationItem["item_key"]) ?? string(enrichedItem["key"]) ?? ""
        let title = string(migrationItem["title"]) ?? string(enrichedItem["title"]) ?? "(untitled)"
        let attachments = enrichedItem["attachments"] as? [[String: Any]] ?? []
        let pdfAttachments = attachments.filter { attachment in
            let contentType = (string(attachment["contentType"]) ?? "").lowercased()
            let filename = (string(attachment["filename"]) ?? "").lowercased()
            return contentType.contains("pdf") || filename.hasSuffix(".pdf")
        }
        let localPDFPaths = pdfAttachments.compactMap { string($0["localPath"]) }.filter { !$0.isEmpty }
        let linkedCount = pdfAttachments.filter { string($0["linkMode"]) == "linked_file" || string($0["path"])?.hasPrefix("attachments:") == true }.count
        let storedCount = pdfAttachments.filter { attachment in
            let linkMode = string(attachment["linkMode"]) ?? ""
            let path = string(attachment["path"]) ?? ""
            return linkMode == "imported_file" || path.hasPrefix("storage:")
        }.count
        let pdfStorageState: String
        if pdfAttachments.isEmpty {
            pdfStorageState = "no PDF"
        } else if storedCount > 0 && linkedCount > 0 {
            pdfStorageState = "\(linkedCount) linked, \(storedCount) stored"
        } else if storedCount > 0 {
            pdfStorageState = "\(storedCount) stored"
        } else if linkedCount > 0 || !localPDFPaths.isEmpty {
            pdfStorageState = "\(max(linkedCount, localPDFPaths.count)) linked"
        } else {
            pdfStorageState = "unknown"
        }
        let reading = enrichedItem["reading_activity"] as? [String: Any] ?? [:]
        let noteCount = int(reading["note_count"]) ?? int(enrichedItem["noteCount"]) ?? 0
        let annotationCount = int(reading["annotation_count"]) ?? int(enrichedItem["annotationCount"]) ?? 0
        let highlightCount = int(reading["highlight_count"]) ?? 0
        let underlineCount = int(reading["underline_count"]) ?? 0
        let commentCount = int(reading["comment_count"]) ?? 0
        let currentAbstract = string(enrichedItem["abstractNote"]) ?? ""
        let readingWorkPresent = bool(reading["has_reading_work"])
            || noteCount > 0
            || annotationCount > 0

        var item = CleanupWorkbenchItem(
            itemKey: key,
            title: title,
            currentCollections: stringArray(migrationItem["existing_collection_keys"]),
            plannedCollections: stringArray(migrationItem["target_collections"]),
            normalizedTags: stringArray(migrationItem["normalized_tags"]),
            confidence: double(migrationItem["confidence"]) ?? 0,
            rationale: string(migrationItem["rationale"]) ?? "",
            metadataIssues: stringArray(migrationItem["metadata_issues"]).isEmpty
                ? stringArray(enrichedItem["metadata_issues"])
                : stringArray(migrationItem["metadata_issues"]),
            doi: string(migrationItem["doi_normalized"])
                ?? string(migrationItem["doi"])
                ?? string(enrichedItem["doi_normalized"])
                ?? string(enrichedItem["doi"])
                ?? "",
            arxivID: string(migrationItem["arxiv_id"]) ?? string(enrichedItem["arxiv_id"]) ?? "",
            url: string(migrationItem["url"]) ?? string(enrichedItem["url"]) ?? "",
            publicationTitle: string(migrationItem["publication_title"])
                ?? string(enrichedItem["publicationTitle"])
                ?? "",
            year: string(migrationItem["year"]) ?? string(enrichedItem["year"]) ?? "",
            abstractStatus: bool(migrationItem["abstract_present"])
                || !currentAbstract.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ? "present"
                : "missing",
            currentAbstract: currentAbstract,
            pdfAttachmentStatus: pdfAttachments.isEmpty
                ? "no PDF attachment"
                : "\(pdfAttachments.count) PDF attachment\(pdfAttachments.count == 1 ? "" : "s")",
            pdfStorageState: pdfStorageState,
            noteCount: noteCount,
            annotationCount: annotationCount,
            highlightCount: highlightCount,
            underlineCount: underlineCount,
            commentCount: commentCount,
            childNoteCount: noteCount,
            readingWorkPresent: readingWorkPresent,
            duplicateRole: string(migrationItem["duplicate_role"]) ?? "",
            canonicalItemKey: string(migrationItem["canonical_item_key"]) ?? "",
            localPDFPaths: localPDFPaths
        )

        if let repair = abstractRepair {
            item.proposedAbstract = string(repair["proposed_abstract"]) ?? ""
            item.abstractEvidenceSource = string(repair["evidence_source"]) ?? ""
            item.abstractRepairConfidence = double(repair["confidence"]) ?? 0
        }
        if let repair = metadataRepair {
            item.metadataDiffs = fieldDiffs(repair["updates"])
        }
        return item
    }

    private static func duplicateGroups(
        dataURL: URL,
        migrationItems: [[String: Any]],
        enrichedByKey: [String: [String: Any]],
        rowsByKey: [String: CleanupWorkbenchItem]
    ) -> [DuplicateWorkbenchGroup] {
        guard let dedupe = readJSON(dataURL.appendingPathComponent("dedupe_plan.json")),
              let groups = dedupe["groups"] as? [[String: Any]] else {
            return []
        }
        let migrationByKey = Dictionary(uniqueKeysWithValues: migrationItems.compactMap { row in
            string(row["item_key"]).map { ($0, row) }
        })
        return groups.compactMap { group in
            guard let groupID = string(group["group_id"]),
                  let items = group["items"] as? [[String: Any]] else {
                return nil
            }
            let duplicateItems = items.map { item -> DuplicateWorkbenchItem in
                let key = string(item["item_key"]) ?? ""
                let enriched = enrichedByKey[key] ?? [:]
                let migration = migrationByKey[key] ?? [:]
                let base = rowsByKey[key]
                let attachments = enriched["attachments"] as? [[String: Any]] ?? []
                let localPDFPaths = attachments.compactMap { string($0["localPath"]) }.filter { !$0.isEmpty }
                let reading = item["reading_activity"] as? [String: Any] ?? [:]
                let pdfCount = int(reading["pdf_attachment_count"]) ?? (bool(item["has_pdf_attachment"]) ? 1 : 0)
                return DuplicateWorkbenchItem(
                    itemKey: key,
                    title: string(item["title"]) ?? base?.title ?? "(untitled)",
                    doi: string(item["doi_normalized"]) ?? base?.doi ?? "",
                    arxivID: string(item["arxiv_id"]) ?? base?.arxivID ?? "",
                    url: string(enriched["url"]) ?? base?.url ?? "",
                    year: string(item["year"]) ?? base?.year ?? "",
                    publicationTitle: string(migration["publication_title"])
                        ?? string(enriched["publicationTitle"])
                        ?? base?.publicationTitle
                        ?? "",
                    currentCollections: base?.currentCollections ?? stringArray(migration["existing_collection_keys"]),
                    plannedCollections: base?.plannedCollections ?? stringArray(migration["target_collections"]),
                    metadataScore: string(item["metadata_quality_score"]) ?? "",
                    noteCount: int(reading["note_count"]) ?? 0,
                    annotationCount: int(reading["annotation_count"]) ?? 0,
                    highlightCount: int(reading["highlight_count"]) ?? 0,
                    underlineCount: int(reading["underline_count"]) ?? 0,
                    commentCount: int(reading["comment_count"]) ?? 0,
                    pdfAttachmentCount: pdfCount,
                    pdfStatus: pdfCount > 0 ? "\(pdfCount) PDF attachment\(pdfCount == 1 ? "" : "s")" : "no PDF attachment",
                    localPDFPaths: localPDFPaths,
                    isCanonical: bool(item["is_canonical"]),
                    unsafeToDelete: bool(item["unsafe_to_delete"])
                )
            }
            return DuplicateWorkbenchGroup(
                id: groupID,
                normalizedTitle: string(group["normalized_title"]) ?? "(untitled)",
                matchType: string(group["match_type"]) ?? "",
                canonicalItemKey: string(group["canonical_item_key"]) ?? "",
                recommendedAction: string(group["recommended_action"]) ?? "",
                canonicalReason: string(group["canonical_reason"]) ?? "",
                metadataMergeSuggested: bool(group["metadata_merge_suggested"]),
                suggestedMetadataSourceItemKey: string(group["suggested_metadata_source_item_key"]) ?? "",
                items: duplicateItems
            )
        }
    }

    private static func repairRows(_ url: URL, keyName: String) -> [String: [String: Any]] {
        guard let plan = readJSON(url),
              let rows = plan["repairs"] as? [[String: Any]] else {
            return [:]
        }
        return Dictionary(uniqueKeysWithValues: rows.compactMap { row in
            string(row[keyName]).map { ($0, row) }
        })
    }

    private static func fieldDiffs(_ value: Any?) -> [FieldDiff] {
        guard let updates = value as? [String: Any] else {
            return []
        }
        return updates.keys.sorted().compactMap { field in
            guard let diff = updates[field] as? [String: Any] else {
                return nil
            }
            return FieldDiff(
                field: field,
                before: string(diff["before"]) ?? "",
                after: string(diff["after"]) ?? ""
            )
        }
    }

    private static func readJSONL(_ url: URL) -> [[String: Any]] {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else {
            return []
        }
        return text.split(separator: "\n").compactMap { line in
            guard let data = line.data(using: .utf8) else {
                return nil
            }
            return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        }
    }

    private static func stringArray(_ value: Any?) -> [String] {
        if let values = value as? [String] {
            return values
        }
        if let values = value as? [Any] {
            return values.compactMap { string($0) }
        }
        return []
    }

    private static func string(_ value: Any?) -> String? {
        switch value {
        case let text as String:
            return text
        case let number as NSNumber:
            return number.stringValue
        case .some(let wrapped):
            return String(describing: wrapped)
        case .none:
            return nil
        }
    }

    private static func int(_ value: Any?) -> Int? {
        switch value {
        case let value as Int:
            return value
        case let value as Double:
            return Int(value)
        case let value as NSNumber:
            return value.intValue
        case let value as String:
            return Int(value)
        default:
            return nil
        }
    }

    private static func double(_ value: Any?) -> Double? {
        switch value {
        case let value as Double:
            return value
        case let value as Int:
            return Double(value)
        case let value as NSNumber:
            return value.doubleValue
        case let value as String:
            return Double(value)
        default:
            return nil
        }
    }

    private static func bool(_ value: Any?) -> Bool {
        switch value {
        case let value as Bool:
            return value
        case let value as NSNumber:
            return value.boolValue
        case let value as String:
            return ["true", "yes", "1"].contains(value.lowercased())
        default:
            return false
        }
    }

    private static func modificationDate(_ url: URL) -> Date {
        let values = try? url.resourceValues(forKeys: [.contentModificationDateKey])
        return values?.contentModificationDate ?? .distantPast
    }
}
