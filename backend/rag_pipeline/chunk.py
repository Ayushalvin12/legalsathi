import json
import os
import uuid

input_path = "extraction/criminal_code_flat_sections.json"
output_path = "chunks/criminal_code_chunked_with_all.json"

def chunk_legal_sections(input_file, output_file):
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
            "OriginalID": original_id
        }

        # === Add metadata context to content
        metadata_text = "\n".join([
            f"Part: {metadata['PartID']} - {metadata['PartTitle']}",
            f"Chapter: {metadata['ChapterID']} - {metadata['ChapterTitle']}",
            f"Section: {metadata['SectionID']} - {metadata['SectionTitle']}",
        ])

        content_parts = [metadata_text]  # Include metadata at the top

        if section.get("Description", "").strip():
            content_parts.append(section["Description"].strip())

        for article in section.get("Articles", []):
            art_id = article.get("ArticleID", "NA").strip("()")
            if article.get("Description", "").strip():
                content_parts.append(f"Article {art_id}: {article['Description'].strip()}")

        for sub in section.get("Sub-sections", []):
            sub_id = sub.get("Sub-sectionID", "NA").strip("()")
            if sub.get("Description", "").strip():
                content_parts.append(f"Sub-section {sub_id}: {sub['Description'].strip()}")

            for article in sub.get("Articles", []):
                art_id = article.get("ArticleID", "NA").strip("()")
                if article.get("Description", "").strip():
                    content_parts.append(f"Article {art_id}: {article['Description'].strip()}")

        if content_parts:
            chunks.append({
                "id": chunk_id,
                "title": f"{metadata['PartTitle']} | {metadata['ChapterTitle']} | Section {metadata['SectionID']} - {metadata['SectionTitle']}",
                "content": "\n\n".join(content_parts),
                "metadata": metadata
            })

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    print(f"✅ Chunked {len(chunks)} items into '{output_path}'")

if __name__ == "__main__":
    chunk_legal_sections(input_path, output_path)
