import pdfplumber
import re
import json

pdf_path = "../data/raw/civil_code.pdf"
output_path = "extraction/civil_code_flat_sections.json"

metadata = {}
sections = []

# State variables
current_part = None
current_part_title = ""
current_chapter = None
current_chapter_title = ""
current_section = None
current_section_title = ""
current_description = ""
current_articles = []
current_subsections = []
current_article = None
current_subsection = None

# Regex patterns
part_pattern = re.compile(r'^Part\s*[--]?\s*(\d+)', re.IGNORECASE)
chapter_pattern = re.compile(r'^Chapter\s*[--]?\s*(\d+)', re.IGNORECASE)
section_pattern = re.compile(r'^(\d+)\.\s*([^:]+):\s*(.*)?')
subsection_pattern = re.compile(r'^\((\d+)\)\s+(.*)$')
subclause_pattern = re.compile(r'^\(([a-z])\)\s*(.*)')
metadata_pattern = re.compile(r'^(Date of Authentication|Act number):\s*(.+)$', re.IGNORECASE)
preamble_start_pattern = re.compile(r'^Preamble:', re.IGNORECASE)
page_number_pattern = re.compile(r'^\d{1,3}$')

def flush_section():
    """Push the current section data into the sections list."""
    if current_section:
        section_data = {
            "PartID": current_part,
            "PartTitle": current_part_title,
            "ChapterID": current_chapter,
            "ChapterTitle": current_chapter_title,
            "SectionID": current_section,
            "SectionTitle": current_section_title,
            "Description": current_description.strip(),
        }
        if current_articles:
            section_data["Articles"] = current_articles.copy()
        if current_subsections:
            section_data["Sub-sections"] = current_subsections.copy()
        sections.append(section_data)

try:
    with pdfplumber.open(pdf_path) as pdf:
        lines = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                lines.extend(text.split("\n"))

        next_is_part_title = False
        next_is_chapter_title = False
        in_preamble = False
        preamble_lines = []

        for line in lines:
            line = line.strip()
            if not line or page_number_pattern.match(line):
                continue

            # Metadata
            meta = metadata_pattern.match(line)
            if meta:
                metadata[meta.group(1).replace(" ", "_").lower()] = meta.group(2).strip()
                continue

            # Preamble
            if preamble_start_pattern.match(line):
                in_preamble = True
                preamble_lines.append(line)
                continue
            elif in_preamble:
                if part_pattern.match(line):
                    sections.append({
                        "PartID": None,
                        "PartTitle": None,
                        "ChapterID": None,
                        "ChapterTitle": None,
                        "SectionID": "Preamble",
                        "SectionTitle": "Preamble",
                        "Description": " ".join(preamble_lines).strip()
                    })
                    in_preamble = False
                    preamble_lines = []
                    # process line below
                else:
                    preamble_lines.append(line)
                    continue

            # Part
            match = part_pattern.match(line)
            if match:
                flush_section()
                current_part = f"Part-{match.group(1)}"
                current_part_title = ""
                next_is_part_title = True
                continue
            if next_is_part_title:
                current_part_title = line
                next_is_part_title = False
                continue

            # Chapter
            match = chapter_pattern.match(line)
            if match:
                flush_section()
                current_chapter = f"Chapter-{match.group(1)}"
                current_chapter_title = ""
                next_is_chapter_title = True
                continue
            if next_is_chapter_title:
                current_chapter_title = line
                next_is_chapter_title = False
                continue

            # Section
            match = section_pattern.match(line)
            if match:
                flush_section()
                current_section = f"{match.group(1)}."
                current_section_title = match.group(2).strip()
                raw_text = match.group(3).strip() if match.group(3) else ""
                current_description = ""
                current_articles = []
                current_subsections = []
                current_subsection = None

                # If section text begins with a subsection like (1), treat it as a subsection instead
                first_sub_match = subsection_pattern.match(raw_text)
                if first_sub_match:
                    current_subsection = {
                        "Sub-sectionID": f"({first_sub_match.group(1)})",
                        "Description": first_sub_match.group(2).strip(),
                        "Articles": []
                    }
                    current_subsections.append(current_subsection)
                else:
                    current_description = raw_text
                continue

            # Sub-section
            match = subsection_pattern.match(line)
            if match:
                current_subsection = {
                    "Sub-sectionID": f"({match.group(1)})",
                    "Description": match.group(2).strip(),
                    "Articles": []
                }
                current_subsections.append(current_subsection)
                continue

            # Article
            match = subclause_pattern.match(line)
            if match:
                article = {
                    "ArticleID": f"({match.group(1)})",
                    "Description": match.group(2).strip()
                }
                if current_subsection:
                    current_subsection["Articles"].append(article)
                else:
                    current_articles.append(article)
                continue

            # Continuation line
            if current_subsection and current_subsection.get("Articles"):
                current_subsection["Articles"][-1]["Description"] += " " + line
            elif current_subsection:
                current_subsection["Description"] += " " + line
            elif current_articles:
                current_articles[-1]["Description"] += " " + line
            elif current_section:
                current_description += " " + line

        # Final flush
        flush_section()

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "metadata": metadata,
            "sections": sections
        }, f, ensure_ascii=False, indent=4)

    print(f"✅ Flat section-based JSON saved to {output_path}")

except Exception as e:
    print(f"❌ Error occurred: {str(e)}")
