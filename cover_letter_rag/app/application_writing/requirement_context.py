"""Lossless, source-bound view of EXISTING requirements. No extraction/LLM/DB."""
import hashlib
import json
import re
from app.job_requirements import JobRequirement, requirement_cache_key, REQUIREMENT_PROMPT_VERSION, classify_requirement
from .models import ContextMaterial, RequirementSource

MAX_REQUIREMENT_CONTEXT = 3
NOISE_TOKENS = {'회사','귀사','경험','프로젝트','직무','내용','지원','담당','결과','구현','개발','본인','기술','요건',
                '필수','우대','조건','있으신','분','경험이','기여','the','and','with','api'}


def validate_requirements(value):
    if not isinstance(value,list): raise ValueError('Structured profile must retain its JobRequirement array')
    rows=[JobRequirement.model_validate(item) for item in value]
    ids=[r.id for r in rows]
    if any(not i.strip() for i in ids) or len(ids)!=len(set(ids)):
        raise ValueError('Requirement IDs must be nonempty and unique within profile')
    if any(not r.posting_quote.strip() for r in rows): raise ValueError('Requirement posting_quote required')
    return rows


def requirement_hash(requirement):
    return hashlib.sha256(json.dumps(requirement.model_dump(mode='json'),ensure_ascii=False,
        sort_keys=True,separators=(',',':')).encode()).hexdigest()


def profile_source(context):
    source=context.get('requirement_profile_source')
    if not isinstance(source,dict): raise ValueError('Requirement profile provenance missing')
    if (not context.get('job_id') or not context.get('snapshot_hash') or
        source.get('job_id')!=context['job_id'] or source.get('snapshot_hash')!=context['snapshot_hash'] or
        source.get('profile_key')!=context.get('requirement_profile_key') or
        source.get('profile_key')!=requirement_cache_key(dict(job_id=context['job_id'],snapshot_hash=context['snapshot_hash'])) or
        source.get('prompt_version')!=REQUIREMENT_PROMPT_VERSION):
        raise ValueError('Stale/mismatched requirement profile identity')
    return source


def resolve_requirement(context, material, application_id):
    source=profile_source(context); provenance=material.requirement_source
    rows=validate_requirements(context.get('requirements'))
    found=next((r for r in rows if r.id==material.material_id),None)
    if found is None or provenance is None: raise ValueError('Unknown requirement reference')
    if (material.source_type!='target_context' or material.answer_index is not None or
        material.source_path!=['requirements','id:'+found.id,'posting_quote'] or
        provenance.application_id!=application_id or provenance.profile_key!=source['profile_key'] or
        provenance.snapshot_hash!=source['snapshot_hash'] or provenance.prompt_version!=source['prompt_version'] or
        provenance.requirement!=found or provenance.requirement_hash!=requirement_hash(found) or
        material.source_quote!=found.posting_quote or material.normalized_text!=context_text(found)):
        raise ValueError('Changed/mixed requirement material or stale source')
    return found


def context_text(row):
    return f'[{row.group}; {row.kind}] {row.label}: {row.posting_quote}'


def tokens(text):
    return {v.casefold() for v in re.findall(r'[A-Za-z][A-Za-z0-9_+.#-]*|[가-힣]{2,}',text)}-NOISE_TOKENS


def overlap(needles,text):
    haystack=re.sub(r'\s+','',text).casefold()
    return sum(1 for token in needles if token in haystack)


def directly_asks_eligibility(row, question):
    # A career project question is not a career-duration/eligibility question.
    rules=[(r'학사|학력|졸업|전공|석사|박사',r'학력|학위|학사|석사|박사|졸업\s*여부|전공\s*(?:명|분야|은)'),
           (r'병역',r'병역|군필|면제'),(r'자격증|면허',r'자격증|면허'),
           (r'경력|신입',r'경력\s*(?:연수|기간|년수|조건|자격)|몇\s*년|신입|경력.{0,8}(?:년|개월)'),
           (r'어학|TOEIC|OPIc',r'어학|TOEIC|OPIc')]
    return any(re.search(label,row.label,re.I) and re.search(ask,question,re.I) for label,ask in rules)


def build_requirement_materials(data,plan,questions):
    if not data.target_context.get('requirement_profile_key'): return []
    source=profile_source(data.target_context)
    rows=validate_requirements(data.target_context.get('requirements'))
    questions={q.question_id:q for q in questions}
    analyses={q.question_id:q for q in data.questions}
    facts={f.evidence_id:f for e in data.experiences for f in e.evidence}
    output=[]
    for row in plan.assignments:
        q=questions[row.question_id]
        selected=row.core_evidence_ids+row.supporting_evidence_ids+row.result_evidence_ids
        # Relevance ONLY: no must/preferred numeric ranking; no unselected experience.
        signals=tokens(' '.join([q.raw_text,row.story_focus]+[facts[i].normalized_fact for i in selected]))
        relevant=[]
        for req in rows:
            # Old extraction caches can retain default kind=skill: classification
            # happens AFTER cache save in v1. Reuse its Python guard for selection
            # only, without rewriting the stored kind or source record.
            eligibility=req.kind=='eligibility' or classify_requirement(req.label)[0]=='eligibility'
            eligibility_requested=eligibility and directly_asks_eligibility(req,q.raw_text)
            if eligibility and not eligibility_requested: continue
            hits=overlap(signals,req.label+' '+req.posting_quote)
            if eligibility_requested: hits=max(1,hits)
            if hits: relevant.append((hits,req))
        relevant.sort(key=lambda item:(-item[0],item[1].id))
        key=next((a.key for a in analyses[row.question_id].asks_for if a.required),analyses[row.question_id].asks_for[0].key)
        for _,req in relevant[:MAX_REQUIREMENT_CONTEXT]:
            output.append(ContextMaterial(material_id=req.id,source_type='target_context',question_id=row.question_id,key=key,
                normalized_text=context_text(req),source_quote=req.posting_quote,
                source_path=['requirements','id:'+req.id,'posting_quote'],
                requirement_source=RequirementSource(application_id=data.application_id,profile_key=source['profile_key'],
                    snapshot_hash=source['snapshot_hash'],prompt_version=source['prompt_version'],requirement=req,
                    requirement_hash=requirement_hash(req))))
    return output
