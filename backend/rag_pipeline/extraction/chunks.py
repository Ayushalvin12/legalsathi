import json
import os
import uuid


def chunk_legal_sections(data=None, input_file=None, output_file=None):
    if input_file:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)

    chunks = []

    for section in data.get("sections", []):
        chunk_id = str(uuid.uuid4())
        original_id = f"{section.get('PartID', 'None')}_{section.get('ChapterID', 'None')}_{section.get('SectionID', 'None')}"

        # === Metadata block
        metadata = {
            "PartID": section.get("PartID"),
            "PartTitle": section.get("PartTitle"),
            "ChapterID": section.get("ChapterID"),
            "ChapterTitle": section.get("ChapterTitle"),
            "SectionID": section.get("SectionID"),
            "SectionTitle": section.get("SectionTitle"),
            "OriginalID": original_id,
        }

        # === Add metadata context to content
        metadata_text = "\n".join(
            [
                f"Part: {metadata['PartID']} - {metadata['PartTitle']}",
                f"Chapter: {metadata['ChapterID']} - {metadata['ChapterTitle']}",
                f"Section: {metadata['SectionID']} - {metadata['SectionTitle']}",
            ]
        )

        content_parts = [metadata_text]  # Include metadata at the top

        if section.get("Description", "").strip():
            content_parts.append(section["Description"].strip())

        for clause in section.get("Clauses", []):
            clause_id = clause.get("ClauseID", "NA").strip("()")
            if clause.get("Description", "").strip():
                content_parts.append(
                    f"Clause {clause_id}: {clause['Description'].strip()}"
                )

        for sub in section.get("Sub-sections", []):
            sub_id = sub.get("Sub-sectionID", "NA").strip("()")
            if sub.get("Description", "").strip():
                content_parts.append(
                    f"Sub-section {sub_id}: {sub['Description'].strip()}"
                )

            for clause in sub.get("Clauses", []):
                clause_id = clause.get("ClauseID", "NA").strip("()")
                if clause.get("Description", "").strip():
                    content_parts.append(
                        f"clause {clause_id}: {clause['Description'].strip()}"
                    )

        if content_parts:
            chunks.append(
                {
                    "id": chunk_id,
                    "title": f"{metadata['PartTitle']} | {metadata['ChapterTitle']} | Section {metadata['SectionID']} - {metadata['SectionTitle']}",
                    "content": "\n\n".join(content_parts),
                    "metadata": metadata,
                }
            )

    if output_file:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(chunks, f, indent=2, ensure_ascii=False)

    print(f"✅ Chunked {len(chunks)} items into '{output_file}'")
    print(chunks)
    return chunks


if __name__ == "__main__":
    input_path = "extraction/test_extraction.json"
    output_path = "extraction/criminal_code_chunked_with_metadata.json"
    chunk_legal_sections(input_file=input_path, output_file=output_path)
