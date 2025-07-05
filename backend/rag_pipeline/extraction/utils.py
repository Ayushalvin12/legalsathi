import json
import os

def reset_state(state, level):
    if level in ['part', 'chapter', 'section']:
        state['current_section'] = None
        state['current_section_title'] = ''
        state['current_description'] = ''
        state['current_clauses'] = []
        state['subsections'] = []
        state['current_subsection'] = None
        state['title_buffer'] = []
        state['awaiting_title_completion'] = False
        state['in_subsection_description'] = False
        state['in_explanation'] = False
        state['last_subsection_number'] = 0
        state['in_clause_context'] = False
    if level in ['part', 'chapter']:
        state['current_chapter'] = None
        state['current_chapter_title'] = ''
    if level == 'part':
        state['current_part_title'] = ''

def flush_section(state):
    if state['current_section']:
        section_data = {
            'PartID': state['current_part'],
            'PartTitle': state['current_part_title'],
            'ChapterID': state['current_chapter'],
            'ChapterTitle': state['current_chapter_title'],
            'SectionID': state['current_section'],
            'SectionTitle': state['current_section_title'].strip().rstrip(':'),
            'Description': state['current_description'].strip()
        }
        if state['current_clauses']:
            section_data['Clauses'] = state['current_clauses'].copy()
        if state['subsections']:
            section_data['Sub-sections'] = state['subsections'].copy()
        state['sections'].append(section_data)

def is_title_complete(line):
    return ':' in line or line.endswith(':')

def write_output(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)