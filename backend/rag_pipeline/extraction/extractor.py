import pdfplumber
import json
import os
import traceback
from patterns import (
    part_pattern, chapter_pattern, section_pattern, subsection_pattern,
    subclause_pattern, metadata_pattern, preamble_start_pattern,
    page_number_pattern, section_like_pattern
)

# File paths
pdf_path = r'E:\legal_sathi\data\raw\criminal-code-nepal-new.pdf'
output_path = 'extraction/criminial_code_flat_sections.json'

# State variables
metadata = []
sections = []
current_part = current_part_title = None
current_chapter = current_chapter_title = None
current_section = current_section_title = ''
current_description = ''
current_articles = []
subsections = []
current_subsection = None
in_table_of_contents = True
title_buffer = []
awaiting_title_completion = False
in_subsection_description = False
in_explanation = False
last_subsection_number = 0
in_article_context = False

def reset_state(level):
    global current_part_title, current_chapter, current_chapter_title
    global current_section, current_section_title, current_description
    global current_articles, subsections, current_subsection
    global title_buffer, awaiting_title_completion, in_subsection_description
    global in_explanation, last_subsection_number, in_article_context

    if level in ['part', 'chapter', 'section']:
        current_section = None
        current_section_title = ''
        current_description = ''
        current_articles = []
        subsections = []
        current_subsection = None
        title_buffer = []
        awaiting_title_completion = False
        in_subsection_description = False
        in_explanation = False
        last_subsection_number = 0
        in_article_context = False
    if level in ['part', 'chapter']:
        current_chapter = None
        current_chapter_title = ''
    if level == 'part':
        current_part_title = ''

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

def is_title_complete(line):
    return ':' in line or line.endswith(':')

def write_output(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

try:
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f'PDF file not found: {pdf_path}')

    with pdfplumber.open(pdf_path) as pdf:
        lines = [line.strip() for page in pdf.pages for line in page.extract_text().split('\n') if page.extract_text()]

        next_is_part_title = next_is_chapter_title = in_preamble = False
        preamble_lines = []

        for line in lines:
            if not line or page_number_pattern.match(line):
                continue

            if in_table_of_contents:
                if preamble_start_pattern.match(line) or part_pattern.match(line) or chapter_pattern.match(line):
                    in_table_of_contents = False
                else:
                    continue

            if meta := metadata_pattern.match(line):
                metadata.append({meta.group(1).replace(' ', '_').lower(): meta.group(2).strip()})
                continue

            if preamble_start_pattern.match(line):
                in_preamble = True
                preamble_lines.append(line)
                continue
            elif in_preamble:
                if part_pattern.match(line) or chapter_pattern.match(line):
                    sections.append({
                        'PartID': None, 'PartTitle': None, 'ChapterID': None,
                        'ChapterTitle': None, 'SectionID': 'Preamble',
                        'SectionTitle': 'Preamble',
                        'Description': ' '.join(preamble_lines).strip()
                    })
                    in_preamble = False
                    preamble_lines = []
                else:
                    preamble_lines.append(line)
                    continue

            if match := part_pattern.match(line):
                flush_section()
                reset_state('part')
                current_part = f'Part-{match.group(1)}'
                next_is_part_title = True
                continue
            if next_is_part_title:
                current_part_title = line
                next_is_part_title = False
                continue

            if match := chapter_pattern.match(line):
                flush_section()
                reset_state('chapter')
                current_chapter = f'Chapter-{match.group(1)}'
                next_is_chapter_title = True
                continue
            if next_is_chapter_title:
                current_chapter_title = line.strip()
                next_is_chapter_title = False
                continue

            if match := section_pattern.match(line):
                flush_section()
                reset_state('section')
                current_section = f'{match.group(1)}.'
                current_section_title = match.group(2).strip()
                raw_text = match.group(3).strip() if match.group(3) else ''
                title_buffer = [current_section_title]
                awaiting_title_completion = not is_title_complete(line)

                if first_sub := subsection_pattern.match(raw_text):
                    current_subsection = {
                        'Sub-sectionID': f'({first_sub.group(1)})',
                        'Description': first_sub.group(2).strip(),
                        'Articles': []
                    }
                    subsections.append(current_subsection)
                    last_subsection_number = int(first_sub.group(1))
                else:
                    current_description = raw_text
                continue

            if current_section and awaiting_title_completion and not any(
                p.match(line) for p in [subsection_pattern, subclause_pattern, section_like_pattern, part_pattern, chapter_pattern]
            ):
                parts = line.split(':', 1)
                title_buffer.append(parts[0].strip())
                current_section_title = ' '.join(title_buffer).strip()
                if is_title_complete(line):
                    awaiting_title_completion = False
                    if len(parts) > 1 and parts[1].strip():
                        if sub_match := subsection_pattern.match(parts[1].strip()):
                            current_subsection = {
                                'Sub-sectionID': f'({sub_match.group(1)})',
                                'Description': sub_match.group(2).strip(),
                                'Articles': []
                            }
                            subsections.append(current_subsection)
                            last_subsection_number = int(sub_match.group(1))
                        else:
                            current_description = parts[1].strip()
                continue

            if match := subclause_pattern.match(line):
                article = {'ArticleID': f'({match.group(1)})', 'Description': match.group(2).strip()}
                (current_subsection['Articles'] if current_subsection else current_articles).append(article)
                awaiting_title_completion = False
                in_subsection_description = True
                in_explanation = False
                in_article_context = True
                continue

            # Explanation
            if 'Explanation:' in line:
                in_explanation = True
                in_article_context = False
                explanation_text = line.strip()
                if current_subsection and current_subsection.get('Articles'):
                    current_subsection['Articles'][-1]['Description'] += ' ' + explanation_text
                elif current_articles:
                    current_articles[-1]['Description'] += ' ' + explanation_text
                elif current_subsection:
                    current_subsection['Description'] += ' ' + explanation_text
                elif current_section:
                    current_description += ' ' + explanation_text
                continue

            # Sub-section or bullet point
            if match := subsection_pattern.match(line):
                subsection_number = int(match.group(1))
                subsection_text = match.group(2).strip()

                if in_explanation:
                    # Stop explanation if this is long or looks like a new sub-section
                    if len(subsection_text.split()) > 12 or subsection_text[0].isupper():
                        in_explanation = False
                    else:
                        if current_subsection and current_subsection.get('Articles'):
                            current_subsection['Articles'][-1]['Description'] += f' ({subsection_number}) {subsection_text}'
                        elif current_articles:
                            current_articles[-1]['Description'] += f' ({subsection_number}) {subsection_text}'
                        elif current_subsection:
                            current_subsection['Description'] += f' ({subsection_number}) {subsection_text}'
                        continue

                # ➤ NEW: If we're in an article, these are just nested points
                if in_article_context and current_articles:
                    current_articles[-1]['Description'] += f' ({subsection_number}) {subsection_text}'
                    continue

                # ➤ Otherwise start a real new sub-section
                in_explanation = False
                in_article_context = False
                if subsection_number > last_subsection_number:
                    current_subsection = {
                        'Sub-sectionID': f'({match.group(1)})',
                        'Description': subsection_text,
                        'Articles': []
                    }
                    subsections.append(current_subsection)
                    last_subsection_number = subsection_number
                    awaiting_title_completion = False
                    in_subsection_description = True
                else:
                    (current_subsection or current_section)['Description'] += ' ' + line
                continue

            if section_like_pattern.match(line):
                flush_section()
                match = section_pattern.match(line) or section_like_pattern.match(line)
                current_section = f'{match.group(1)}.'
                current_section_title = line[len(current_section):].rstrip(':').strip()
                reset_state('section')
                continue

            # Continuation lines
            if in_explanation:
                if current_subsection and current_subsection.get('Articles'):
                    current_subsection['Articles'][-1]['Description'] += ' ' + line
                elif current_articles:
                    current_articles[-1]['Description'] += ' ' + line
                elif current_subsection:
                    current_subsection['Description'] += ' ' + line
                elif current_section:
                    current_description += ' ' + line
                continue

            if current_subsection and current_subsection.get('Articles'):
                current_subsection['Articles'][-1]['Description'] += ' ' + line
            elif current_subsection:
                current_subsection['Description'] += ' ' + line
            elif current_articles:
                current_articles[-1]['Description'] += ' ' + line
            elif current_section:
                current_description += ' ' + line
                awaiting_title_completion = False

        flush_section()
        write_output(output_path, {'metadata': metadata, 'sections': sections})
        print(f'✅ JSON saved to {output_path}')

except Exception as e:
    print(f'❌ Error: {str(e)}')
    traceback.print_exc()
