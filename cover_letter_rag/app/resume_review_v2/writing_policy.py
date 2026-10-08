"""Section policy and conservative quality candidates, not a semantic judge.

Evidence count alone is never a prose defect.
"""
import re
from difflib import SequenceMatcher
from .models import ValidationIssue, FactType
from .policy import (SECTION_RULES, ENUMERATION_LIMIT, REDUNDANCY_THRESHOLD,
                     REPORT_VERB_LIMIT, CHRONOLOGY_LIMIT)


def target_section(experience):
    path = experience.field_path
    if path.startswith('selfIntroduction.'):
        return {'motivation': 'motivation', 'aspiration': 'future_plan',
                'strengthsWeaknesses': 'strength_weakness', 'challenge': 'challenge',
                'growth': 'growth', 'intro': 'self_intro'}.get(path.split('.')[1], 'self_intro')
    if path.startswith('projects['):
        return 'project'
    if path.startswith(('experience[', 'career[')):
        return 'career'
    if path.startswith(('trainingExperience[', 'education[')):
        return 'education'
    return {'project': 'project', 'employment': 'career', 'education': 'education',
            'activity': 'activity'}.get(experience.kind, 'other')


def quality_candidates(experience, writer, evidence=None):
    text = writer.suggested_text
    section = target_section(experience)
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', text) if s.strip()]
    issues = []
    def flag(code, detail):
        if code not in {i.code for i in issues}:
            issues.append(ValidationIssue(code=code, detail=detail))
    for i, sentence in enumerate(sentences):
        for previous in sentences[:i]:
            a, b = re.sub(r'\W+', '', previous), re.sub(r'\W+', '', sentence)
            if min(len(a), len(b)) >= 18 and SequenceMatcher(None, a, b).ratio() >= REDUNDANCY_THRESHOLD:
                flag('semantic_redundancy', 'near-duplicate contribution sentences; lexical candidate')
    if section == 'project' and re.search(r'계획입니다|예정입니다|하고자 합니다', text) and not re.search(r'했습니다|하였습니다|구현한|설계한', text):
        flag('section_mismatch', 'project contribution replaced by future intentions')
    if any(len(re.findall(r'[,、·]|\s및\s', s)) >= ENUMERATION_LIMIT for s in sentences):
        flag('excessive_enumeration', 'long flat enumeration instead of implementation-focused synthesis')
    chronology = len(re.findall(r'먼저|그다음|이후|한 뒤|하고 나서|마지막으로|했으며|하였으며|하면서', text))
    # Citation structure, not a magic word in the prose, identifies substantive
    # reasoning. The semantic verifier still checks that cited meaning is expressed.
    cited = {eid for sentence in writer.sentences for eid in sentence.evidence_ids}
    reasoning = any(eid in cited and fact.fact_type in
                    {FactType.TECHNICAL_DECISION, FactType.VERIFICATION, FactType.RESULT}
                    for eid, fact in (evidence or {}).items())
    if section == 'project' and not reasoning and len(re.findall(r'(?:확인|판단|검토|파악)(?:했습니다|하였습니다)', text)) >= REPORT_VERB_LIMIT:
        flag('report_like_prose', 'repeated reporting verbs without visible problem-solving detail')
    if section == 'project' and chronology >= CHRONOLOGY_LIMIT and not reasoning:
        flag('unnecessary_chronology', 'routine chronology without visible problem-solving rationale')
        flag('procedure_overload', 'implementation expressed as procedural chronology')
    steps = re.findall(r'전처리|분할|적재|재?색인|저장', text)
    if section == 'project' and not reasoning and len(sentences) >= 3 and len(steps) >= 4 and len(set(steps)) < len(steps):
        flag('procedure_overload', 'repeated handling steps across three or more sentences')
    filler = re.findall(r'다양한 경험|여러 기술|여러 모델|많은 작업|전반적인|관련 작업|역량을 강화', text)
    concrete = re.search(r'[A-Za-z][A-Za-z0-9_-]{2,}|\d|구현|설계|분석|연동|최적화|거리|캐싱', text)
    if section == 'project' and len(filler) >= 2 and not concrete:
        flag('low_information_density', 'generic claims without concrete contribution or technical signal')
    details = len(re.findall(r'불필요한 (?:부분|내용|영역)|필요 없는 (?:부분|내용)|다시 (?:저장|정리)|파일을 (?:열|읽)', text))
    if section == 'project' and details >= 2 and chronology >= 2 and not reasoning:
        flag('low_value_detail_retention', 'routine handling details dominate project prose')
    return issues
