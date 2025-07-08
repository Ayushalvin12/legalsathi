import re

part_pattern = re.compile(r'^Part\s*[\u2013\-]?\s*(\d+)', re.I)
chapter_pattern = re.compile(r'^Chapter\s*[\u2013\-]?\s*(\d+|[IVX]+|[A-Z])\b', re.I)
section_pattern = re.compile(r'(?<!\w)(\d+)\.\s*([^:\n]+?)(?::\s*(.*))?$')
subsection_pattern = re.compile(r'^\((\d+)\)\s*(.*)$')
subclause_pattern = re.compile(r'^\(([a-z]+)\)\s*(.*)')
metadata_pattern = re.compile(r'^(Date of Authentication|Act number):\s*(.+)$', re.I)
metadata_key_pattern = re.compile(r'^(Date of Authentication|Act number):$', re.I)
preamble_start_pattern = re.compile(r'^Preamble:', re.I)
page_number_pattern = re.compile(r'^\d{1,3}$')
section_like_pattern = re.compile(r'(?<!\w)(\d+)\.\s+[^:\n]+')
