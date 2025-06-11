import pdfplumber
import re
import json
import os

pdf_path = r'E:\legal_sathi\data\raw\civil_code.pdf'
output_path = 'extraction/civil_code_flat_sections.json'

metadata = []
sections = []

# State variables
current_part = None
current_part_title = ''
current_chapter = None
current_chapter_title = ''
current_section = None
current_section_title = ''
current_description = ''
current_articles = []
subsections = []
current_subsection = None
in_table_of_contents = True
title_buffer = []
awaiting_title_completion = False
in_subsection_description = False

# Regex patterns
part_pattern = re.compile(r'^Part\s*[–\-]?\s*(\d+)', re.I)
chapter_pattern = re.compile(r'^Chapter\s*[–\-]?\s*(\d+|[A-Za-z]+)', re.I)
section_pattern = re.compile(r'(?<!\w)(\d+)\.\s*([^:\n]+?)(?::\s*(.*))?$')
subsection_pattern = re.compile(r'^\((\d+)\)\s*(.*)$')
subclause_pattern = re.compile(r'^\(([a-z])\)\s*(.*)')
metadata_pattern = re.compile(r'^(Date of Authentication|Act number):\s*(.+)$', re.I)
preamble_start_pattern = re.compile(r'^Preamble:', re.I)
page_number_pattern = re.compile(r'^\d{1,3}$')
section_like_pattern = re.compile(r'(?<!\w)(\d+)\.\s+[^:\n]+')

def flush_section():
    if current_section:
        section_data = {
            'PartID': current_part,
            'PartTitle': current_part_title,
            'ChapterID': current_chapter,
            'ChapterTitle': current_chapter_title,
            'SectionID': current_section,
            'SectionTitle': current_section_title.strip().rstrip(':'),
            'Description': current_description.strip()
        }
        if current_articles:
            section_data['Articles'] = current_articles.copy()
        if subsections:
            section_data['Sub-sections'] = subsections.copy()
        sections.append(section_data)

try:
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f'PDF file not found: {pdf_path}')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with pdfplumber.open(pdf_path) as pdf:
        lines = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                lines.extend(text.split('\n'))

        next_is_part_title = next_is_chapter_title = in_preamble = False
        preamble_lines = []

        for line in lines:
            line = line.strip()
            if not line or page_number_pattern.match(line):
                continue

            # Skip Table of Contents
            if in_table_of_contents:
                if preamble_start_pattern.match(line) or part_pattern.match(line):
                    in_table_of_contents = False
                else:
                    continue

            # Metadata
            if meta := metadata_pattern.match(line):
                metadata.append({meta.group(1).replace(' ', '_').lower(): meta.group(2).strip()})
                continue

            # Preamble
            if preamble_start_pattern.match(line):
                in_preamble = True
                preamble_lines.append(line)
                continue
            elif in_preamble:
                if part_pattern.match(line):
                    sections.append({
                        'PartID': None,
                        'PartTitle': None,
                        'ChapterID': None,
                        'ChapterTitle': None,
                        'SectionID': 'Preamble',
                        'SectionTitle': 'Preamble',
                        'Description': ' '.join(preamble_lines).strip()
                    })
                    in_preamble = False
                    preamble_lines = []
                else:
                    preamble_lines.append(line)
                    continue

            # Part
            if match := part_pattern.match(line):
                flush_section()
                current_part = f'Part-{match.group(1)}'
                current_part_title = ''
                current_chapter = None
                current_chapter_title = ''
                current_section = None
                current_section_title = ''
                current_description = ''
                current_articles = []
                subsections = []
                current_subsection = None
                next_is_part_title = True
                title_buffer = []
                awaiting_title_completion = False
                in_subsection_description = False
                continue
            if next_is_part_title:
                current_part_title = line
                next_is_part_title = False
                continue

            # Chapter
            if match := chapter_pattern.match(line):
                flush_section()
                current_chapter = f'Chapter-{match.group(1)}'
                current_chapter_title = ''
                current_section = None
                current_section_title = ''
                current_description = ''
                current_articles = []
                subsections = []
                current_subsection = None
                next_is_chapter_title = True
                title_buffer = []
                awaiting_title_completion = False
                in_subsection_description = False
                continue
            if next_is_chapter_title:
                current_chapter_title = line.strip()
                next_is_chapter_title = False
                continue

            # Section
            if match := section_pattern.match(line):
                flush_section()
                current_section = f'{match.group(1)}.'
                current_section_title = match.group(2).strip()
                raw_text = match.group(3).strip() if match.group(3) else ''
                current_description = ''
                current_articles = []
                subsections = []
                current_subsection = None
                title_buffer = [current_section_title]
                awaiting_title_completion = ':' not in line and not line.endswith(':')
                in_subsection_description = False
                if first_sub_match := subsection_pattern.match(raw_text):
                    current_subsection = {
                        'Sub-sectionID': f'({first_sub_match.group(1)})',
                        'Description': first_sub_match.group(2).strip(),
                        'Articles': []
                    }
                    subsections.append(current_subsection)
                    current_description = ''
                else:
                    current_description = raw_text
                continue

            # Multi-line section title
            if current_section and awaiting_title_completion and not (subsection_pattern.match(line) or subclause_pattern.match(line) or section_like_pattern.match(line) or part_pattern.match(line) or chapter_pattern.match(line)):
                parts = line.split(':', 1)
                title_buffer.append(parts[0].strip())
                current_section_title = ' '.join(title_buffer).strip()
                if ':' in line or line.endswith(':'):
                    awaiting_title_completion = False
                    if len(parts) > 1 and parts[1].strip():
                        if sub_match := subsection_pattern.match(parts[1].strip()):
                            current_subsection = {
                                'Sub-sectionID': f'({sub_match.group(1)})',
                                'Description': sub_match.group(2).strip(),
                                'Articles': []
                            }
                            subsections.append(current_subsection)
                        else:
                            current_description = parts[1].strip()
                continue

            # Sub-section
            if match := subsection_pattern.match(line):
                if in_subsection_description and current_subsection and not line.startswith('(' + str(int(current_subsection['Sub-sectionID'][1:-1]) + 1) + ')'):
                    current_subsection['Description'] += ' ' + line
                    continue
                current_subsection = {
                    'Sub-sectionID': f'({match.group(1)})',
                    'Description': match.group(2).strip(),
                    'Articles': []
                }
                subsections.append(current_subsection)
                awaiting_title_completion = False
                in_subsection_description = True
                continue

            # Article
            if match := subclause_pattern.match(line):
                article = {
                    'ArticleID': f'({match.group(1)})',
                    'Description': match.group(2).strip()
                }
                (current_subsection['Articles'] if current_subsection else current_articles).append(article)
                awaiting_title_completion = False
                in_subsection_description = True
                continue

            # Section-like header
            if section_like_pattern.match(line):
                flush_section()
                match = section_pattern.match(line) or section_like_pattern.match(line)
                current_section = f'{match.group(1)}.'
                current_section_title = line[len(current_section):].rstrip(':').strip()
                current_description = ''
                current_articles = []
                subsections = []
                current_subsection = None
                title_buffer = [current_section_title]
                awaiting_title_completion = ':' not in line and not line.endswith(':')
                in_subsection_description = False
                continue

            # Append to description, but check for chapter first
            if chapter_pattern.match(line):
                flush_section()
                current_chapter = f'Chapter-{chapter_pattern.match(line).group(1)}'
                current_chapter_title = ''
                current_section = None
                current_section_title = ''
                current_description = ''
                current_articles = []
                subsections = []
                current_subsection = None
                next_is_chapter_title = True
                title_buffer = []
                awaiting_title_completion = False
                in_subsection_description = False
                continue

            if current_subsection and current_subsection.get('Articles'):
                current_subsection['Articles'][-1]['Description'] += ' ' + line
            elif current_subsection:
                current_subsection['Description'] += ' ' + line
                in_subsection_description = True
            elif current_articles:
                current_articles[-1]['Description'] += ' ' + line
            elif current_section:
                current_description += ' ' + line
                awaiting_title_completion = False

        # Final flush
        flush_section()

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({'metadata': metadata, 'sections': sections}, f, ensure_ascii=False, indent=4)

    print(f'✅ JSON saved to {output_path}')

except Exception as e:
    print(f'❌ Error: {str(e)}')