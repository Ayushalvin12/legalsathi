import pdfplumber
import os
import traceback
from patterns import (
    part_pattern, chapter_pattern, section_pattern, subsection_pattern,
    subclause_pattern, metadata_pattern, metadata_key_pattern, preamble_start_pattern,
    page_number_pattern, section_like_pattern
)
from utils import reset_state, flush_section, is_title_complete, write_output

# File paths
pdf_path = r'E:\legal_sathi\data\raw\civil_code_debug.pdf'
output_path = 'extraction/test_debug.json'

# State dictionary
state = {
    'metadata': [],
    'sections': [],
    'current_part': None,
    'current_part_title': None,
    'current_chapter': None,
    'current_chapter_title': None,
    'current_section': None,
    'current_section_title': '',
    'current_description': '',
    'current_clauses': [],
    'subsections': [],
    'current_subsection': None,
    'in_table_of_contents': True,
    'title_buffer': [],
    'awaiting_title_completion': False,
    'in_subsection_description': False,
    'in_explanation': False,
    'last_subsection_number': 0,
    'in_clause_context': False
}
current_meta_key = None

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

            # Check for metadata key lines (no value yet)
            if key_match := metadata_key_pattern.match(line):
                current_meta_key = key_match.group(1)
                continue

            # If previous line was a metadata key, this is its value
            if current_meta_key:
                state['metadata'].append({
                    current_meta_key.replace(' ', '_').lower(): line.strip()
                })
                current_meta_key = None
                continue

            if meta := metadata_pattern.match(line):
                state['metadata'].append({meta.group(1).replace(' ', '_').lower(): meta.group(2).strip()})
                continue

            if state['in_table_of_contents']:
                if preamble_start_pattern.match(line) or part_pattern.match(line) or chapter_pattern.match(line):
                    state['in_table_of_contents'] = False
                else:
                    continue

            if preamble_start_pattern.match(line):
                in_preamble = True
                preamble_lines.append(line)
                continue
            elif in_preamble:
                if part_pattern.match(line) or chapter_pattern.match(line):
                    state['sections'].append({
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
                flush_section(state)
                reset_state(state, 'part')
                state['current_part'] = f'Part-{match.group(1)}'
                next_is_part_title = True
                continue
            if next_is_part_title:
                state['current_part_title'] = line
                next_is_part_title = False
                continue

            if match := chapter_pattern.match(line):
                flush_section(state)
                reset_state(state, 'chapter')
                state['current_chapter'] = f'Chapter-{match.group(1)}'
                next_is_chapter_title = True
                continue
            if next_is_chapter_title:
                state['current_chapter_title'] = line.strip()
                next_is_chapter_title = False
                continue

            if match := section_pattern.match(line):
                flush_section(state)
                reset_state(state, 'section')
                state['current_section'] = f'{match.group(1)}.'
                state['current_section_title'] = match.group(2).strip()
                raw_text = match.group(3).strip() if match.group(3) else ''
                state['title_buffer'] = [state['current_section_title']]
                state['awaiting_title_completion'] = not is_title_complete(line)

                if first_sub := subsection_pattern.match(raw_text):
                    state['current_subsection'] = {
                        'Sub-sectionID': f'({first_sub.group(1)})',
                        'Description': first_sub.group(2).strip(),
                        'Clauses': []
                    }
                    state['subsections'].append(state['current_subsection'])
                    state['last_subsection_number'] = int(first_sub.group(1))
                else:
                    state['current_description'] = raw_text
                continue

            if state['current_section'] and state['awaiting_title_completion'] and not any(
                p.match(line) for p in [subsection_pattern, subclause_pattern, section_like_pattern, part_pattern, chapter_pattern]
            ):
                parts = line.split(':', 1)
                state['title_buffer'].append(parts[0].strip())
                state['current_section_title'] = ' '.join(state['title_buffer']).strip()
                if is_title_complete(line):
                    state['awaiting_title_completion'] = False
                    if len(parts) > 1 and parts[1].strip():
                        if sub_match := subsection_pattern.match(parts[1].strip()):
                            state['current_subsection'] = {
                                'Sub-sectionID': f'({sub_match.group(1)})',
                                'Description': sub_match.group(2).strip(),
                                'Clauses': []
                            }
                            state['subsections'].append(state['current_subsection'])
                            state['last_subsection_number'] = int(sub_match.group(1))
                        else:
                            state['current_description'] = parts[1].strip()
                continue

            if match := subclause_pattern.match(line):
                clause = {'ClauseID': f'({match.group(1)})', 'Description': match.group(2).strip()}
                (state['current_subsection']['Clauses'] if state['current_subsection'] else state['current_clauses']).append(clause)
                state['awaiting_title_completion'] = False
                state['in_subsection_description'] = True
                state['in_explanation'] = False
                state['in_clause_context'] = True
                continue

            # Explanation
            if 'Explanation:' in line:
                state['in_explanation'] = True
                state['in_clause_context'] = False
                explanation_text = line.strip()
                if state['current_subsection'] and state['current_subsection'].get('Clauses'):
                    state['current_subsection']['Clauses'][-1]['Description'] += ' ' + explanation_text
                elif state['current_clauses']:
                    state['current_clauses'][-1]['Description'] += ' ' + explanation_text
                elif state['current_subsection']:
                    state['current_subsection']['Description'] += ' ' + explanation_text
                elif state['current_section']:
                    state['current_description'] += ' ' + explanation_text
                continue

            # Sub-section or bullet point
            if match := subsection_pattern.match(line):
                subsection_number = int(match.group(1))
                subsection_text = match.group(2).strip()

                if state['in_explanation']:
                    # Stop explanation if this is long or looks like a new sub-section
                    if len(subsection_text.split()) > 12 or subsection_text[0].isupper():
                        state['in_explanation'] = False
                    else:
                        if state['current_subsection'] and state['current_subsection'].get('Clauses'):
                            state['current_subsection']['Clauses'][-1]['Description'] += f' ({subsection_number}) {subsection_text}'
                        elif state['current_clauses']:
                            state['current_clauses'][-1]['Description'] += f' ({subsection_number}) {subsection_text}'
                        elif state['current_subsection']:
                            state['current_subsection']['Description'] += f' ({subsection_number}) {subsection_text}'
                        continue

                # If we're in a clause, these are just nested points
                if state['in_clause_context'] and state['current_clauses']:
                    state['current_clauses'][-1]['Description'] += f' ({subsection_number}) {subsection_text}'
                    continue

                # Otherwise start a real new sub-section
                state['in_explanation'] = False
                state['in_clause_context'] = False
                if subsection_number > state['last_subsection_number']:
                    state['current_subsection'] = {
                        'Sub-sectionID': f'({match.group(1)})',
                        'Description': subsection_text,
                        'Clauses': []
                    }
                    state['subsections'].append(state['current_subsection'])
                    state['last_subsection_number'] = subsection_number
                    state['awaiting_title_completion'] = False
                    state['in_subsection_description'] = True
                else:
                    (state['current_subsection'] or {'Description': state['current_description']})['Description'] += ' ' + line
                continue

            if section_like_pattern.match(line):
                flush_section(state)
                match = section_pattern.match(line) or section_like_pattern.match(line)
                state['current_section'] = f'{match.group(1)}.'
                state['current_section_title'] = line[len(state['current_section']):].rstrip(':').strip()
                reset_state(state, 'section')
                continue

            # Continuation lines
            if state['in_explanation']:
                if state['current_subsection'] and state['current_subsection'].get('Clauses'):
                    state['current_subsection']['Clauses'][-1]['Description'] += ' ' + line
                elif state['current_clauses']:
                    state['current_clauses'][-1]['Description'] += ' ' + line
                elif state['current_subsection']:
                    state['current_subsection']['Description'] += ' ' + line
                elif state['current_section']:
                    state['current_description'] += ' ' + line
                continue

            if state['current_subsection'] and state['current_subsection'].get('Clauses'):
                state['current_subsection']['Clauses'][-1]['Description'] += ' ' + line
            elif state['current_subsection']:
                state['current_subsection']['Description'] += ' ' + line
            elif state['current_clauses']:
                state['current_clauses'][-1]['Description'] += ' ' + line
            elif state['current_section']:
                state['current_description'] += ' ' + line
                state['awaiting_title_completion'] = False

        flush_section(state)
        write_output(output_path, {'metadata': state['metadata'], 'sections': state['sections']})
        print(f'✅ JSON saved to {output_path}')

except Exception as e:
    print(f'❌ Error: {str(e)}')
    traceback.print_exc()