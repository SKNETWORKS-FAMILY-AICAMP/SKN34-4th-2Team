"""Text/section parsing only. No LLM, Experience, Evidence or job dependencies."""
import hashlib
import re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MAX_DOCUMENT_BYTES = 2_000_000
HEADINGS = {
    '핵심역량': 'core', '경력사항': 'experience', '경력': 'experience',
    '학력': 'education', '학력사항': 'education', '기술': 'techStack', '기술스택': 'techStack',
    '자격': 'certifications', '자격사항': 'certifications', '교육': 'trainingExperience',
    '교육경험': 'trainingExperience', '기타활동': 'otherActivities', '수상': 'awards',
    '자기소개': 'intro', '지원동기': 'motivation', '어려움극복사례': 'challenge',
    '성장과정': 'growth', '성격의장단점': 'strengthsWeaknesses', '입사후포부': 'aspiration',
    '프로젝트경험': 'projects', '프로젝트': 'projects',
}
INTRO_KEYS = ('intro', 'motivation', 'challenge', 'growth', 'strengthsWeaknesses', 'aspiration')


def read_document(path):
    path = Path(path)
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError('Document too large')
    if path.suffix.lower() == '.txt':
        return path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() != '.docx':
        raise ValueError('Only DOCX and UTF-8 TXT documents supported')
    with ZipFile(path) as archive:
        entry = archive.getinfo('word/document.xml')
        if entry.file_size > MAX_DOCUMENT_BYTES:
            raise ValueError('Expanded document too large')
        root = ET.fromstring(archive.read(entry))
    paragraphs = []
    # Includes paragraphs inside tables, preserving document order and breaks.
    for paragraph in root.iter(W+'p'):
        text = ''.join(node.text or '' if node.tag == W+'t' else '\n' if node.tag == W+'br' else '\t'
                       for node in paragraph.iter() if node.tag in {W+'t', W+'br', W+'tab'})
        if text.strip():
            paragraphs.append(text)
    return '\n'.join(paragraphs)


def parse_text(text, *, source_id):
    """Recognize explicit headings; never classify statements or infer skills/roles."""
    if not text.strip():
        raise ValueError('Empty document')
    content = {'basicInfo': {k: '' for k in ('name', 'phone', 'email', 'birthDate', 'githubUrl', 'blogUrl')},
        'coreCompetencies': {'text': ''},
        **{k: [] for k in ('experience', 'education', 'techStack', 'certifications', 'awards', 'trainingExperience', 'otherActivities', 'projects')},
        'selfIntroduction': {k: {'subtitle': '', 'body': ''} for k in INTRO_KEYS}}
    blocks, preamble, current = [], [], None
    for line in text.splitlines():
        key = re.sub(r'\s+', '', line.strip()).rstrip(':：')
        section = HEADINGS.get(key)
        item_heading = re.fullmatch(r'(프로젝트|경력|교육|기타활동)\s*(\d+)\s*[.、:]\s*(.+)', line.strip())
        if item_heading:
            section = {'프로젝트': 'projects', '경력': 'experience', '교육': 'trainingExperience', '기타활동': 'otherActivities'}[item_heading[1]]
        if section:
            current = {'section': section, 'title': item_heading[3] if item_heading else '', 'lines': []}
            blocks.append(current)
        elif current is None:
            preamble.append(line)
        else:
            current['lines'].append(line)
    if preamble:
        content['basicInfo']['name'] = preamble[0].strip()
    for block in blocks:
        section, lines = block['section'], block['lines']
        value = '\n'.join(lines).strip()
        if section == 'core':
            content['coreCompetencies']['text'] += ('\n' if content['coreCompetencies']['text'] else '')+value
            continue
        if section in INTRO_KEYS:
            body = content['selfIntroduction'][section]['body']
            content['selfIntroduction'][section]['body'] = body+('\n' if body else '')+value
            continue
        entries = [re.sub(r'^\s*[•·*-]\s*', '', line).strip() for line in lines if line.strip()]
        if section in {'techStack', 'certifications', 'education'}:
            for entry in entries:
                for name in (entry.split(',') if section == 'techStack' else [entry]):
                    if section == 'techStack': item = {'name': name.strip(), 'level': ''}
                    elif section == 'certifications': item = {'name': name, 'issuer': '', 'acquiredDate': ''}
                    else: item = {'school': name, 'major': '', 'startDate': '', 'endDate': '', 'status': ''}
                    content[section].append(item)
            continue
        if not block['title'] and not entries:
            continue
        title = block['title'] or entries[0]
        description = value if block['title'] else '\n'.join(lines[1:]).strip()
        common = {'startDate': '', 'endDate': '', 'description': description}
        if section == 'projects': item = {**common, 'name': title, 'role': '', 'techStack': '', 'url': ''}
        elif section == 'experience': item = {**common, 'company': title, 'role': '', 'isCurrent': False}
        elif section == 'trainingExperience': item = {**common, 'course': title, 'organization': ''}
        elif section == 'awards': item = {'name': title, 'organization': '', 'date': '', 'description': description}
        else: item = {**common, 'name': title}
        content[section].append(item)
    prefix = hashlib.sha256(source_id.encode()).hexdigest()[:10]
    for section, items in content.items():
        if isinstance(items, list):
            for index, item in enumerate(items):
                item['id'] = f'local-{prefix}-{section}-{index+1}'
    return content


def document_bundle(path, *, title, source_id):
    text = read_document(path)
    return {'version': 1, 'permission': 'self', 'source_resume_id': source_id,
        'source_text': text, 'resume': {'title': title, 'content': parse_text(text, source_id=source_id)}}
