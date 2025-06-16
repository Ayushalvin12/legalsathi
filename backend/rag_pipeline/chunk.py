"""
import json

input_path = "../extraction/civil_code_flat_sections.json"
output_path = "../chunks/civil_code_chunked.json"

def chunk_legal_sections(input_file, output_file):
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = []

    for section in data.get("sections", []):
        parts = []

        if section.get("PartTitle"):
            parts.append(section["PartTitle"])

        if section.get("ChapterTitle"):
            parts.append(section["ChapterTitle"])

        if section.get("SectionID") and section.get("SectionTitle"):
            parts.append(f"Section {section['SectionID']}-{section['SectionTitle']}")

        title = " | ".join(parts) if parts else section.get("SectionTitle", "Untitled")

        content = []
        if "Description" in section:
            content.append(section["Description"])

        for sub in section.get("Sub-sections", []):
            content.append(f"{sub.get('Sub-sectionID', '')} {sub.get('Description', '')}".strip())

        for article in section.get("Articles", []):
            content.append(f"{article.get('ArticleID', '')} {article.get('Description', '')}".strip())

        full_content = "\n".join(content)

        chunks.append({
            "id": f"{section.get('PartID', 'NA')}_{section.get('ChapterID', 'NA')}_{section.get('SectionID', 'NA')}",
            "title": title,
            "content": full_content
        })

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    print(f"✅ Chunked {len(chunks)} items into '{output_file}'")


if __name__ == "__main__":
    chunk_legal_sections(input_path, output_path)
  
"""


import json
import os

input_path = "extraction/civil_code_flat_sections.json"
output_path = "chunks/civil_code_chunked.json"


def chunk_legal_sections(input_file, output_file):
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = []

    for section in data.get("sections", []):
        base_id = f"{section.get('PartID', 'NA')}_{section.get('ChapterID', 'NA')}_{section.get('SectionID', 'NA')}"
        base_title_parts = []

        if section.get("PartTitle"):
            base_title_parts.append(section["PartTitle"])
        if section.get("ChapterTitle"):
            base_title_parts.append(section["ChapterTitle"])
        if section.get("SectionID") and section.get("SectionTitle"):
            base_title_parts.append(f"Section {section['SectionID']} - {section['SectionTitle']}")

        base_title = " | ".join(base_title_parts) if base_title_parts else section.get("SectionTitle", "Untitled")

        # Common metadata
        common_meta = {
            "PartID": section.get("PartID", "NA"),
            "PartTitle": section.get("PartTitle", "NA"),
            "ChapterID": section.get("ChapterID", "NA"),
            "ChapterTitle": section.get("ChapterTitle", "NA"),
            "SectionID": section.get("SectionID", "NA"),
            "SectionTitle": section.get("SectionTitle", "NA")
        }

        has_subs = section.get("Sub-sections")
        has_articles = section.get("Articles")

        # ✅ Whole-section chunk if no sub-sections or articles
        if not has_subs and not has_articles:
            chunks.append({
                "id": base_id,
                "title": base_title,
                "content": section.get("Description", "").strip(),
                "metadata": common_meta
            })

        # ✅ Chunk each sub-section
        if has_subs:
            for sub in section["Sub-sections"]:
                sub_id = sub.get("Sub-sectionID", "NA").strip("()")
                full_id = f"{base_id}_Sub_{sub_id}"

                title = f"{base_title} | Sub-section {sub.get('Sub-sectionID', '')}"
                content = sub.get("Description", "")

                chunk_meta = {
                    **common_meta,
                    "Sub-sectionID": sub.get("Sub-sectionID", "NA"),
                    "Sub-sectionTitle": content[:50] + "..." if content else "NA"
                }

                chunks.append({
                    "id": full_id,
                    "title": title,
                    "content": content.strip(),
                    "metadata": chunk_meta
                })

                # ✅ Articles under sub-sections
                for article in sub.get("Articles", []):
                    art_id = article.get("ArticleID", "NA").strip("()")
                    art_full_id = f"{full_id}_Art_{art_id}"

                    art_title = f"{title} | Article {article.get('ArticleID', '')}"
                    art_content = article.get("Description", "")

                    chunk_meta = {
                        **chunk_meta,
                        "ArticleID": article.get("ArticleID", "NA"),
                        "ArticleTitle": art_content[:50] + "..." if art_content else "NA"
                    }

                    chunks.append({
                        "id": art_full_id,
                        "title": art_title,
                        "content": art_content.strip(),
                        "metadata": chunk_meta
                    })

        # ✅ Top-level articles in section
        if has_articles:
            for article in section["Articles"]:
                art_id = article.get("ArticleID", "NA").strip("()")
                full_id = f"{base_id}_Art_{art_id}"

                art_title = f"{base_title} | Article {article.get('ArticleID', '')}"
                art_content = article.get("Description", "")

                chunk_meta = {
                    **common_meta,
                    "ArticleID": article.get("ArticleID", "NA"),
                    "ArticleTitle": art_content[:50] + "..." if art_content else "NA"
                }

                chunks.append({
                    "id": full_id,
                    "title": art_title,
                    "content": art_content.strip(),
                    "metadata": chunk_meta
                })

    # Save output
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    print(f"✅ Chunked {len(chunks)} items into '{output_file}'")

if __name__ == "__main__":
    chunk_legal_sections(input_path, output_path)
