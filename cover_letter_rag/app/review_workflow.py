"""Versioned review orchestration; raw credentials/content never enter telemetry."""
import hashlib
import json
import re
import time
from difflib import SequenceMatcher

from app.models import (
    Diagnostic, FirestoreResumeReviewResponse, NewResumeItem, ResumeReviewGeneration, ReviewQuestion, SentenceReview,
)
from app.prompts import ANSWER_FLOW_RULE, MIXED_ANSWER_RULE, NEW_PROJECT_RULE, UNCERTAIN_ANSWER_RULE
from app.review_rules import (
    EXPERIENCE_DESCRIPTION, EXPERIENCE_ITEM, EXPERIENCE_SECTION_PATTERN, GENERIC_NAME_TOKENS, ITEM_NAME_KEYS,
    NARRATIVE_FIELD, NEW_PROJECT_NAME_GENERIC, PROJECT_FORM_WORDS, ROLE_EXPANSION_WORDS, SECTION_NAMES,
    noun_fragment_sentences, split_uncertain_answer,
)
from app.technology import technology_mentions
from app.star_checks import (
    STAR_LABELS, STAR_TARGET, ground_star_judgements, has_elements, mark_answered_star_elements, star_by_path, star_targets,
)
from app.job_requirements import (
    JobRequirement,
    classify_requirements, ground_requirement_matches, load_or_extract_requirements,
    mark_requirement_absent, requirements_prompt_text,
)

PROMPT_VERSION = 'resume-v16y-check-and-repair'
CRITERIA = ('aspiration', 'emotion', 'abstract_result', 'ordering', 'relevance', 'duplication', 'company_fit')
MISSING_JOB_TECH_REASON = '공고에 언급된 기술의 실제 사용 프로젝트를 확인합니다.'


class ReviewConflict(Exception):
    pass


class ReviewInputError(Exception):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def redact(text):
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[연락처 삭제]', text)
    return re.sub(r'(?<!\d)(?:\+82[- .]?|0)(?:10|11|16|17|18|19|2|[3-6][1-5])[- .]?\d{3,4}[- .]?\d{4}(?!\d)', '[연락처 삭제]', text)


def normalize_confirmed_answer(text):
    """Remove requests to fabricate; only user-confirmed facts may ground edits."""
    cleaned = redact(text.strip())
    fabrication_request = re.search(
        r'(지어\s*내|꾸며\s*(?:내|줘|작성)|허구|가짜|임의로\s*(?:만들|작성)|만들어\s*줘)',
        cleaned,
        re.IGNORECASE,
    )
    if fabrication_request:
        return '사용자가 확인 가능한 추가 사실이 없다고 답했습니다.'
    return cleaned


_RECRUITING_TITLE_SUFFIX = re.compile(
    r'\s*(?:을|를)?\s*(?:찾고\s*있(?:어요|습니다)|모십니다|모집합니다|채용합니다|채용|모집)\s*[.!]?$',
    re.IGNORECASE,
)
_RECRUITING_CONDITION_BRACKET = re.compile(
    r'[\(\[【][^()\[\]【】]*(?:신입|경력|주니어|시니어|인턴|정규직|계약직|채용|모집|무관|이상|년차|'
    r'서울|경기|인천|부산|대구|대전|광주|울산|세종|지역|재택|급구|마감)[^()\[\]【】]*[\)\]】]'
)
_RECRUITING_TITLE_PREFIX = re.compile(
    r'^(?:(?:에서|와|과)\s*)?(?:함께할|함께\s*일할|모실)\s*',
    re.IGNORECASE,
)


def _has_final_consonant(text):
    """Return whether the final Hangul syllable has a 받침.

    English/acronym-ending role names have no reliable Korean particle rule, so
    use the vowel-ending form as the least intrusive fallback.
    """
    match = re.search(r'[가-힣]$', str(text or '').strip())
    return bool(match and (ord(match.group()) - ord('가')) % 28)


def _job_role_with_particle(role, particle):
    """Attach a natural Korean particle to a selected-job role title."""
    has_batchim = _has_final_consonant(role)
    if particle in ('은', '는', '이', '가'):
        # 직무 자체를 주어로 쓸 때는 'AI 엔지니어은'이 아니라
        # 'AI 엔지니어 직무는'이 가장 자연스럽다.
        return f'{role} 직무는'
    if particle in ('을', '를'):
        return f"{role}{'을' if has_batchim else '를'}"
    if particle in ('으로', '로'):
        # 받침 ㄹ 뒤에는 '로', 그 밖의 받침 뒤에는 '으로'를 쓴다.
        last = str(role or '').strip()[-1:]
        is_rieul = bool(last and '가' <= last <= '힣' and (ord(last) - ord('가')) % 28 == 8)
        return f"{role}{'로' if not has_batchim or is_rieul else '으로'}"
    return f'{role}{particle}'


def job_role_title(company, posting_title):
    """사람인 전체 공고 제목에서 이력서에 넣을 실제 직무명만 추린다."""
    company = str(company or '').strip()
    title = re.sub(r'\s+', ' ', str(posting_title or '')).strip()
    if not title:
        return ''

    role = title
    if company:
        role = re.sub(re.escape(company), ' ', role, flags=re.IGNORECASE)
    role = re.sub(r'^\s*(?:에서|와|과)\s*', '', role)
    role = _RECRUITING_TITLE_PREFIX.sub('', role)
    # "(신입)", "(경력 3년 이상)", "[서울]"처럼 모집 조건을 담은 괄호는 직무명이 아니다. 그대로 두면
    # "공공 SI 사업 Java 개발자 (신입)에 지원하게 되었습니다"가 된다(2026-09-14 목업 첨삭).
    role = _RECRUITING_CONDITION_BRACKET.sub(' ', role)
    role = _RECRUITING_TITLE_SUFFIX.sub('', role)
    role = re.sub(r'^[\s|·:/_-]+|[\s|·:/_-]+$', '', role)
    # 붙여 쓰인 대표 직무 표기는 이력서에서 읽기 좋은 형태로 통일한다.
    role = re.sub(r'(?i)(AI|ML|IT)\s*(엔지니어|개발자)', r'\1 \2', role)
    return re.sub(r'\s+', ' ', role).strip() or title


def review_job_prompt_text(job_text, job_source):
    """Mark selected-job identity as trusted context, separate from resume facts."""
    if not job_text:
        return '제공되지 않음'
    if not job_source:
        return job_text
    company = str(job_source.get('company') or '').strip() or '확인 불가'
    title = str(job_source.get('title') or '').strip() or '확인 불가'
    role_title = str(job_source.get('role_title') or '').strip() or job_role_title(company, title)
    return (
        '[선택 공고 식별 정보 — 사용자가 선택한 확정값]\n'
        f'회사명: {company}\n'
        f'직무명: {role_title}\n'
        f'공고 제목: {title}\n\n'
        '[공고 원문]\n'
        f'{job_text}'
    )


_IDENTITY_QUESTION_PATTERN = re.compile(r'(회사명|회사\s*이름|지원\s*회사|직무명|직무\s*이름|지원\s*직무)')
_PROJECT_TIME_QUESTION_PATTERN = re.compile(r'(시작일|종료일|기간|진행\s*상태|진행\s*여부|미래\s*기간|완료\s*여부)')


def project_time_context(content):
    """Return recorded project periods without inferring their present status."""
    entries = []
    for index, project in enumerate((content or {}).get('projects') or []):
        if not isinstance(project, dict):
            continue
        start = str(project.get('startDate') or '').strip()
        end = str(project.get('endDate') or '').strip()
        if not start or not end:
            continue
        entries.append({
            'field_prefix': f'projects[{index}]',
            'name': str(project.get('name') or '').strip() or f'프로젝트 {index + 1}',
            'start': start,
            'end': end,
        })
    if not entries:
        return '확정 가능한 프로젝트 기간이 없습니다.'
    return '\n'.join(
        f"{entry['field_prefix']} {entry['name']}: {entry['start']} ~ {entry['end']} (이력서 기록값)"
        for entry in entries
    )


def filter_verified_project_time_questions(generation, context):
    """Do not ask the user to reconfirm a project period already calculated."""
    verified_prefixes = {
        line.split(' ', 1)[0]
        for line in context.splitlines()
        if line.startswith('projects[') and '이력서 기록값' in line
    }
    if not verified_prefixes:
        return
    generation.questions = [
        question for question in generation.questions
        if not (
            any(question.field_path.startswith(prefix) for prefix in verified_prefixes)
            and _PROJECT_TIME_QUESTION_PATTERN.search(question.question)
        )
    ]


# "…하고 싶어서 지원하게 되었습니다."처럼 지원 사실만 적고 회사·직무는 빠진 마무리 문장.
# 어미를 그대로 두고 그 앞에만 회사명·직무명을 끼워 넣으려고 끝 부분만 잡는다.
_IDENTITY_APPLY_TAIL = re.compile(
    r'지원(?:하게\s*되었습니다|하게\s*됐습니다|하게\s*되었어요|했습니다|하였습니다|합니다|하고자\s*합니다)'
    r'\s*[.!?]?\s*$'
)


# 이유를 잇는 "-아서/어서"가 줄어든 꼴은 "서" 앞이 받침 없는 ㅏ·ㅓ·ㅕ·ㅐ·ㅘ·ㅝ다.
# (싶어서·맞아서·위해서·배워서·만들어서…) 한글 음절을 풀어 이 모양일 때만 "서"를 뗀다.
# 조사 "에서"(ㅔ), 연결어미 "-면서"(받침 있음), "로서"(ㅗ)는 이 조건에 걸리지 않는다.
_CAUSAL_VOWELS = frozenset({0, 1, 4, 6, 9, 14})  # ㅏ ㅐ ㅓ ㅕ ㅘ ㅝ
# 위 조건에는 걸리지만 "서"를 떼면 말이 안 되는 접속부사.
_CAUSAL_SHORTEN_BLOCKED = ('그래서', '따라서')


def _is_causal_seo(syllable):
    """이 글자가 "-아서/어서"의 줄어든 꼴 끝인가. 받침이 없고 모음이 위 여섯 중 하나여야 한다."""
    code = ord(syllable) - 0xAC00
    if not 0 <= code < 11172:
        return False
    return code % 28 == 0 and (code // 28) % 21 in _CAUSAL_VOWELS


def _shorten_causal_ending(head):
    """끼워 넣을 자리 바로 앞의 "-아서/어서"를 "-아/어"로 줄인다.

    회사명·직무명이 들어가면 문장이 길어지는데, "-어서"와 "지원하게 되었습니다"가 둘 다 이유를
    짚어 늘어진다. 줄이면 앞말이 뒷말에 그대로 이어진다. 바로 앞 한 곳만 건드린다.
    """
    stripped = head.rstrip()
    if len(stripped) < 2 or not stripped.endswith('서'):
        return head
    if stripped.endswith(_CAUSAL_SHORTEN_BLOCKED) or not _is_causal_seo(stripped[-2]):
        return head
    return stripped[:-1] + head[len(stripped):]


def _weave_identity_into_application(text, company, title):
    """지원 사실만 적힌 마무리 문장 안에 회사명·직무명을 끼워 넣는다.

    문장을 하나 더 붙이는 대신 있는 문장을 쓰므로 첫 첨삭 결과가 바로 읽을 만해진다.
    어미는 손대지 않는다. 직무명이 이미 적혀 있으면 같은 말이 두 번 나오므로 하지 않는다.
    끼워 넣을 자리가 없으면 None을 돌려주고, 부르는 쪽이 독립 문장을 앞에 붙인다.
    """
    body = str(text or '').rstrip()
    if not body.strip() or title in body:
        return None
    match = _IDENTITY_APPLY_TAIL.search(body)
    if not match:
        return None
    role_label = title if title.endswith('직무') else f'{title} 직무'
    head = _shorten_causal_ending(body[:match.start()])
    # 앞말과 붙어 버리지 않게 한 칸 띄운다. 문장 맨 앞이면 띄우지 않는다.
    separator = '' if not head or head.endswith((' ', '\n')) else ' '
    return f'{head}{separator}{company}의 {role_label}에 {body[match.start():]}'


def apply_selected_job_identity_revisions(
    generation,
    fields,
    job_source,
    *,
    insert_missing_identity=False,
):
    """Replace resume placeholders from the selected job without asking the user.

    Company and role are selected-job facts, not resume facts. Placeholder
    replacement and the optional tailored-resume introduction are deterministic;
    neither depends on an LLM following a prompt instruction.
    """
    company = str(job_source.get('company') or '').strip()
    posting_title = str(job_source.get('title') or '').strip()
    title = str(job_source.get('role_title') or '').strip() or job_role_title(
        company,
        posting_title,
    )
    replacements = {}
    auto_identity_paths = set()
    woven_identity_paths = set()
    for field_path, original in fields.items():
        revised = original
        changed = []
        # 자리표시자 뒤의 조사를 직무명 마지막 글자에 맞게 바꾼다.
        # 예: 'AI 엔지니어은' → 'AI 엔지니어 직무는',
        #     'AI 엔지니어으로' → 'AI 엔지니어로'.
        if company and title:
            placeholder_with_particle = re.compile(
                r'\[회사명\]\s*의\s*\[직무명\]\s*(?P<particle>으로|은|는|이|가|을|를|로)'
            )
            if placeholder_with_particle.search(revised):
                revised = placeholder_with_particle.sub(
                    lambda match: f"{company}의 {_job_role_with_particle(title, match.group('particle'))}",
                    revised,
                )
                changed.extend(['회사명', '직무명'])
        if company and '[회사명]' in revised:
            revised = revised.replace('[회사명]', company)
            changed.append('회사명')
        if title and '[직무명]' in revised:
            revised = revised.replace('[직무명]', title)
            changed.append('직무명')
        # 구 버전에서 [직무명] 자리에 전체 공고 제목을 넣은 이력서도 복구한다.
        if posting_title and title and posting_title != title and posting_title in revised:
            revised = revised.replace(posting_title, title)
            if '직무명' not in changed:
                changed.append('직무명')
        # 이미 잘못 치환된 이력서도 같은 표현으로 복구한다.
        if company and title:
            role_candidates = [title]
            if posting_title and posting_title != title:
                role_candidates.append(posting_title)
            role_pattern = '|'.join(re.escape(candidate) for candidate in role_candidates)
            job_subject = re.compile(
                rf'{re.escape(company)}\s*의\s*(?:{role_pattern})\s*(?:은|는|이|가)'
            )
            if job_subject.search(revised):
                revised = job_subject.sub(f'{company}의 {title} 직무는', revised)
                if '직무명' not in changed:
                    changed.append('직무명')
        if changed:
            replacements[field_path] = (original, revised, '·'.join(changed))

    # 기본 이력서에 자리표시자를 쓰도록 강요하지 않는다. 공고별 사본의 첫 검토에서만
    # 지원동기(없으면 입사 후 포부) 한 곳에 안전한 독립 문장을 제안한다. 원문과 문장을
    # 억지로 이어 붙이지 않아 어떤 내용이 뒤따라도 조사나 의미가 깨지지 않는다.
    has_identity_replacement = bool(replacements)
    # 'AI 엔지니어' 같은 범용 희망 직무는 기본 이력서에도 흔히 존재한다.
    # 선택 회사명이 실제로 들어간 경우에만 이미 공고 맞춤 반영된 것으로 본다.
    identity_already_written = bool(company) and any(
        company in value for value in fields.values()
    )
    if (
        insert_missing_identity
        and company
        and title
        and not has_identity_replacement
        and not identity_already_written
    ):
        candidate_paths = (
            'selfIntroduction.motivation.body',
            'selfIntroduction.aspiration.body',
        )
        field_path = next(
            (path for path in candidate_paths if str(fields.get(path) or '').strip()),
            None,
        )
        if field_path:
            original = fields[field_path]
            # 있는 문장 안에 넣을 수 있으면 그렇게 한다. 독립 문장을 앞에 붙이면 "…지원한 이유는 다음과
            # 같습니다. / …지원하게 되었습니다."처럼 지원 얘기가 두 번 나와, 사용자가 다음 첨삭에서 합치는
            # 수정안을 한 번 더 받아야 했다(2026-09-16 앱 확인). 어미는 건드리지 않아 조사·의미는 그대로다.
            woven = _weave_identity_into_application(original, company, title)
            if woven:
                replacements[field_path] = (original, woven, '회사명·직무명')
                woven_identity_paths.add(field_path)
            else:
                if field_path.endswith('.motivation.body'):
                    role_label = title if title.endswith('직무') else f'{title} 직무'
                    identity_sentence = f'{company}의 {role_label}에 지원한 이유는 다음과 같습니다.'
                else:
                    identity_sentence = (
                        f'{company}에서 {_job_role_with_particle(title, "으로")} '
                        '성장하고 싶습니다.'
                    )
                replacements[field_path] = (
                    original,
                    f'{identity_sentence}\n{original}',
                    '회사명·직무명',
                )
            auto_identity_paths.add(field_path)
    if not replacements:
        return

    # The deterministic replacement is the only edit for its field. Otherwise a
    # model-generated whole-field rewrite could overwrite it during apply.
    generation.sentence_reviews = [
        review for review in generation.sentence_reviews
        if review.field_path not in replacements
    ]
    for field_path, (original, revised, changed) in replacements.items():
        if field_path in woven_identity_paths:
            reason = '선택한 공고의 회사명·직무명을 지원 문장 안에 넣었습니다.'
        elif field_path in auto_identity_paths:
            reason = (
                '선택한 공고의 회사명·직무명을 공고별 이력서에만 '
                '안전한 문장 패턴으로 추가했습니다.'
            )
        else:
            reason = f'선택한 공고의 {changed} 확정값을 자리표시자에 반영했습니다.'
        generation.sentence_reviews.append(SentenceReview(
            field_path=field_path,
            original_quote=original,
            suggested_revision=revised,
            reason=reason,
            evidence_quotes=[original],
            status='improved',
            edit_type='content',
        ))

    # The company/title are already supplied above; never ask the user for them.
    generation.questions = [
        question for question in generation.questions
        if not _IDENTITY_QUESTION_PATTERN.search(question.question)
    ]
    generation.confirmation_questions = [
        question for question in generation.confirmation_questions
        if not _IDENTITY_QUESTION_PATTERN.search(question)
    ]
    for review in generation.sentence_reviews:
        if review.confirmation_question and _IDENTITY_QUESTION_PATTERN.search(review.confirmation_question):
            review.confirmation_question = None


def group(path):
    return path.rsplit('.', 1)[0]


def focused_followup_context(fields, answers, current_answers):
    """Limit a follow-up model call to the answered resume item.

    Grounding and persistence still receive the complete ``fields`` mapping.
    This only keeps unrelated resume entries out of the next model prompt after
    a user answers a confirmation question.
    """
    target_groups = {group(answer.field_path) for answer in current_answers if answer.field_path in fields}
    if not target_groups:
        return fields, answers, False
    scoped_fields = {
        path: value for path, value in fields.items()
        if group(path) in target_groups
    }
    scoped_answers = [
        answer for answer in answers
        if group(answer.field_path) in target_groups
    ]
    return scoped_fields, scoped_answers, True


def focused_time_context(time_context, current_answers):
    """Keep project-period context aligned with the follow-up resume item."""
    target_groups = {group(answer.field_path) for answer in current_answers}
    if not target_groups:
        return time_context
    lines = [
        line for line in time_context.splitlines()
        if any(line.startswith(target_group + ' ') for target_group in target_groups)
    ]
    return '\n'.join(lines) or '현재 첨삭 항목에 기록된 프로젝트 기간이 없습니다.'


def followup_job_prompt_text(job_text, job_source):
    """Keep selected-job identity in a follow-up without resending its full text."""
    if not job_text:
        return '제공되지 않음'
    if not job_source:
        # Older clients can submit a posting directly without a selected-job id.
        # Preserve a small amount of context, but do not resend a long posting.
        return '[후속 첨삭용 공고 요약]\n' + job_text[:1500]
    company = str(job_source.get('company') or '').strip() or '확인 불가'
    title = str(job_source.get('title') or '').strip() or '확인 불가'
    role_title = str(job_source.get('role_title') or '').strip() or job_role_title(company, title)
    return (
        '[선택 공고 식별 정보 — 사용자가 선택한 확정값]\n'
        f'회사명: {company}\n'
        f'직무명: {role_title}\n'
        f'공고 제목: {title}\n\n'
        '[후속 첨삭용 공고 근거]\n'
        f'{job_text[:2500]}\n\n'
        '[후속 첨삭 범위]\n'
        '위 공고 내용은 회사·직무 맥락에만 사용하고 지원자의 경험으로 쓰지 마세요. '
        '지원자의 경험 근거는 이력서 원문과 이번 사용자 답변에서만 가져오세요.'
    )


def item_references(content, fields):
    refs = {}
    for path in fields:
        match = re.match(r'^(\w+)\[(\d+)\]', path)
        if not match:
            refs[path] = group(path)
            continue
        section, index = match.groups()
        items = content[section]
        item_id = items[int(index)].get('id')
        if not isinstance(item_id, str) or not item_id or sum(i.get('id') == item_id for i in items) != 1:
            refs[path] = 'legacy:' + path  # Answers are explicitly blocked for legacy items.
        else:
            refs[path] = section + ':' + item_id
    return refs


def _project_description_targets(fields):
    targets = []
    indices = sorted({
        int(match.group(1))
        for path in fields
        if (match := re.fullmatch(r'projects\[(\d+)\]\.description', path))
    })
    for index in indices:
        path = f'projects[{index}].description'
        name = str(fields.get(f'projects[{index}].name') or '').strip()
        targets.append((path, name or f'프로젝트 {index + 1}'))
    return targets


def _item_description_targets(fields):
    """기술 요건 답을 옮길 수 있는 경험 칸. 프로젝트 → 경력 → 교육 → 수상 → 활동 순."""
    targets = []
    for section, name_key in ITEM_NAME_KEYS.items():
        indices = sorted({
            int(match.group(1)) for path in fields
            if (match := re.fullmatch(rf'{section}\[(\d+)\]\.description', path))
        })
        for index in indices:
            name = str(fields.get(f'{section}[{index}].{name_key}') or '').strip()
            if name or section == 'projects':
                targets.append((f'{section}[{index}].description', name or f'프로젝트 {index + 1}'))
    return targets


def _name_tokens(name):
    return [token.casefold() for token in re.findall(r'[0-9A-Za-z가-힣+#]{2,}', name)
            if token.casefold() not in GENERIC_NAME_TOKENS]


def resolve_missing_technology_project(answer_text, fields):
    """답에 적힌 항목 이름으로 답을 옮길 칸을 찾는다. 추측으로 고르지 않는다.

    예전에는 질문에 "1번 A, 2번 B"처럼 프로젝트 목록을 붙이고 번호나 이름 전체를 요구했다. 이제 질문은 "어느
    항목에서 했나요?"로만 묻으므로(특정 항목을 지목하지 않는다), 이름의 일부("경진대회 로봇")로도 찾는다.
    이름 낱말이 두 개 이상 답에 있거나, 네 글자 이상 낱말("현장실습", "경진대회")이 답에 있고, 그렇게 가장 많이
    맞는 항목이 하나일 때만 고른다. "개발"·"서비스"처럼 어느 항목에나 붙는 낱말은 세지 않는다.
    """
    targets = _item_description_targets(fields)
    if not targets:
        return None
    project_targets = [target for target in targets if target[0].startswith('projects[')]
    numbered = {
        int(number) - 1
        for number in re.findall(r'(?<!\d)(\d+)\s*번(?:\s*프로젝트)?', answer_text)
    }
    numbered_matches = [target for index, target in enumerate(project_targets) if index in numbered]
    if len(numbered_matches) == 1:
        return numbered_matches[0][0]

    compact_answer = re.sub(r'\s+', '', answer_text).casefold()
    exact = [path for path, name in targets
             if len(re.sub(r'\s+', '', name)) >= 2 and re.sub(r'\s+', '', name).casefold() in compact_answer]
    if len(exact) == 1:
        return exact[0]
    scored = []
    for path, name in targets:
        tokens = _name_tokens(name)
        if not tokens:
            continue
        matched = [token for token in tokens if token in compact_answer]
        if len(matched) >= 2 or any(len(token) >= 4 for token in matched) or (matched and len(matched) == len(tokens)):
            scored.append((len(matched), len(matched) / len(tokens), path))
    if not scored:
        return None
    scored.sort(reverse=True)
    if len(scored) > 1 and scored[0][:2] == scored[1][:2]:
        return None
    return scored[0][2]


# 답변이 이력서에 없는 별도 작업을 말한다는 표시. "부트캠프 개인 과제로", "따로 만든 토이 프로젝트".
_SEPARATE_WORK = re.compile(
    r'(?:개인|토이|사이드|부트캠프|수업|학교|동아리|별도|따로)\s*(?:의\s*)?(?:과제|프로젝트|작업)|혼자\s*만든|따로\s*만든'
)


MAX_MENTIONED_ITEMS = 2


def _item_mention_positions(text, fields):
    """문장에서 경험 항목 이름이 처음 나오는 위치. [(위치, 칸)] 위치 순.

    이름 전체가 있으면 그 자리, 없으면 네 글자 이상의 이름 낱말("현장실습")이 처음 나온 자리를 쓴다.
    """
    lowered = text.casefold()
    found = {}
    for target_path, name in _item_description_targets(fields):
        spaced = re.escape(name.strip()).replace(r'\ ', r'\s*')
        match = re.search(spaced, text, re.IGNORECASE) if name.strip() else None
        position = match.start() if match else None
        if position is None:
            hits = [lowered.find(token) for token in _name_tokens(name) if len(token) >= 4 and token in lowered]
            position = min(hits) if hits else None
        if position is not None:
            found[target_path] = position
    return sorted((position, target_path) for target_path, position in found.items())


def _split_by_item_mentions(sentence, fields):
    """한 문장에 두 항목 이야기가 섞였으면 항목 이름이 나오는 자리에서 나눈다.

    "X에서 처리 시간을 40분에서 10분으로 줄였고, Y에서는 테스트로 검증했습니다"를 문장째 Y에 주면 X의 숫자가 Y 칸
    수정안에 들어가 Y에서 한 일처럼 읽혔다(2026-09-15 한 번도 안 본 케이스). 이름 앞의 말은 앞 조각에 붙인다.
    """
    mentions = _item_mention_positions(sentence, fields)
    if len(mentions) < 2:
        return [sentence]
    cuts = [0] + [position for position, _ in mentions[1:]] + [len(sentence)]
    pieces = [sentence[start:end].strip(' ,') for start, end in zip(cuts, cuts[1:])]
    return [piece for piece in pieces if len(piece) >= 4]


def mentioned_item_answers(current_answers, fields, refs, previous):
    """이번 답에서 질문한 항목이 아닌 다른 경험 항목을 이름으로 말한 문장을, 그 항목에 붙인 답으로 만든다.

    후속 첨삭은 속도 때문에 답한 항목만 모델에 보여 준다. 그래서 "LMS에서 X를 했고, 숙소 예약 클론에서도 Y를 했어요"의
    Y는 넣을 곳이 없어 사라졌다(2026-09-15). 항목 이름이 문장에 분명히 나올 때만(resolve_missing_technology_project와 같은
    기준) 그 문장만 그 항목의 답으로 붙인다. 다른 문장은 옮기지 않아 사실이 섞이지 않게 한다. 저장하지 않고 이번 재첨삭의
    모델 입력·근거 검증에만 쓴다.
    """
    from app.resume_review import _split_answer_sentences

    item_refs = (previous or {}).get('item_refs', {})
    extra = []
    for answer in current_answers:
        if is_none_answer(answer.answer):
            continue
        by_path = {}
        pieces = [piece for sentence in _split_answer_sentences(answer.answer)
                  for piece in _split_by_item_mentions(sentence, fields)]
        for piece in pieces:
            path = resolve_missing_technology_project(piece, fields)
            if not path or group(path) == group(answer.field_path):
                continue
            if refs.get(path, 'legacy:').startswith('legacy:') or item_refs.get(path) != refs[path]:
                continue
            by_path.setdefault(path, []).append(piece)
        for path, sentences in list(by_path.items())[:MAX_MENTIONED_ITEMS]:
            extra.append(answer.model_copy(update={
                'question_id': None, 'field_path': path, 'answer': ' '.join(sentences),
            }))
    return extra


def noun_fragment_targets(fields):
    """첫 첨삭에서 서술문으로 이어야 할 끊긴 문장 목록. [{field_path, sentence}]"""
    return [{'field_path': path, 'sentence': sentence}
            for path, value in fields.items() if NARRATIVE_FIELD.fullmatch(path)
            for sentence in noun_fragment_sentences(value)]


def count_unjoined_fragments(targets, sentence_reviews):
    """목록의 끊긴 문장 중 이어 준 수정안이 없는 수. 측정용으로 telemetry에 남긴다."""
    squash = lambda text: re.sub(r'\s+', '', str(text or ''))  # noqa: E731
    missed = 0
    for target in targets:
        joined = any(
            review.field_path == target['field_path'] and review.suggested_revision
            and squash(target['sentence']) in squash(review.original_quote)
            and squash(target['sentence']) not in squash(review.suggested_revision)
            for review in sentence_reviews
        )
        missed += not joined
    return missed


def without_mentioned_sentences(answers, mentioned_answers, fields):
    """다른 항목으로 떼어 낸 문장을 원래 답에서 뺀다. 문장이 모두 빠진 답은 목록에서 뺀다.

    떼어 낸 문장을 질문한 칸의 근거에도 그대로 두면, 모델이 그 문장을 질문한 칸 수정안에도 넣었다. 교육 칸 질문에 회사
    프로젝트에서 한 일을 답하자 그 문장이 교육 설명에도 들어가 교육 과정에서 한 일처럼 읽혔다(2026-09-15 한 번도 안 본
    케이스). 저장하는 답은 그대로 두고, 이번 재첨삭의 모델 입력·근거 검증에만 쓴다.
    """
    from app.resume_review import _split_answer_sentences

    moved_paths = {answer.field_path for answer in mentioned_answers}
    if not moved_paths:
        return list(answers)
    trimmed = []
    for answer in answers:
        # 자기소개서·핵심역량은 원래 경험을 가리키며 쓰는 칸이라 다른 항목 이야기를 근거에서 빼지 않는다. 뺐더니 자기소개
        # 답("사내 규정 챗봇에서 정답률을 62%에서 81%로")으로 만든 자기소개 수정안이 막혔다(2026-09-15 개발용 v16v).
        if not EXPERIENCE_DESCRIPTION.fullmatch(answer.field_path):
            trimmed.append(answer)
            continue
        # mentioned_item_answers와 같은 기준으로 나눈 조각 중, 다른 항목으로 떼어 낸 조각만 뺀다.
        pieces = [piece for sentence in _split_answer_sentences(answer.answer)
                  for piece in _split_by_item_mentions(sentence, fields)]
        kept = []
        for piece in pieces:
            target = resolve_missing_technology_project(piece, fields)
            if target in moved_paths and group(target) != group(answer.field_path):
                continue
            kept.append(piece)
        if len(kept) == len(pieces):
            trimmed.append(answer)
        elif kept:
            trimmed.append(answer.model_copy(update={'answer': ' '.join(kept)}))
    return trimmed


def withhold_moved_sentences(generation, answered_paths, mentioned_answers, fields):
    """질문한 칸 수정안에 다른 항목으로 떼어 낸 문장이 들어가면 그 수정안을 뺀다. 확인 질문은 붙이지 않는다."""
    from app.resume_review import _split_answer_sentences

    squash = lambda text: re.sub(r'[\s\W_]+', '', str(text or '')).casefold()  # noqa: E731
    warnings = []
    for mentioned in mentioned_answers:
        match = EXPERIENCE_DESCRIPTION.fullmatch(mentioned.field_path)
        name = squash(fields.get(f'{match.group(1)}[{match.group(2)}].{ITEM_NAME_KEYS[match.group(1)]}')) if match else ''
        moved = [squash(sentence) for sentence in _split_answer_sentences(mentioned.answer)]
        for review in generation.sentence_reviews:
            revision = review.suggested_revision
            if (not revision or review.new_item is not None or review.field_path not in answered_paths
                    or not EXPERIENCE_DESCRIPTION.fullmatch(review.field_path)
                    or group(review.field_path) == group(mentioned.field_path)):
                continue
            names_other_item = bool(name) and name in squash(revision) and name not in squash(review.original_quote)
            copies_sentence = any(
                SequenceMatcher(None, squash(sentence), moved_sentence).ratio() >= 0.6
                for sentence in _split_answer_sentences(revision) for moved_sentence in moved
            )
            if names_other_item or copies_sentence:
                review.suggested_revision = None
                review.status = 'unchanged'
                review.edit_type = 'none'
                review.confirmation_question = None
                review.validation_issues = [*review.validation_issues, 'moved_to_other_item']
                warnings.append(f'다른 항목 이야기가 들어간 수정안을 제외했습니다: {review.field_path}')
    return warnings


def add_new_project_proposals(generation, fields, raw_content, answers, previous_questions=None):
    """답변이 기존 항목에 없는 별도 경험이면, 모델이 낸 새 프로젝트 제안을 검증해 수정안으로 만든다.

    "매물 검색 서비스(4인 팀)에서는 지도 API를 안 썼고, 부트캠프 개인 과제로 카카오맵 마커 화면을 만들었다"는 답은
    기존 프로젝트에 넣으면 팀 프로젝트에서 한 일처럼 읽히고, 넣을 칸이 없어 버려졌다(2026-09-15 새 케이스, 답 반영 False).
    이름·설명·기술은 답변에 적힌 말만 허용한다. 기존 프로젝트와 같은 이름이면 새로 만들지 않는다. 턴마다 하나까지.
    수정안을 만든 답변의 question_id 집합을 돌려준다(그 답으로 기존 칸을 채우는 대체 수정안을 만들지 않게).
    """
    from app.resume_review import _cross_field_overlap, _unsupported_numbers
    from app.technology import grounding_terms

    proposals, generation.new_projects = list(generation.new_projects), []
    warnings, used = [], set()
    if not proposals or not answers or not isinstance(raw_content, dict):
        return warnings, used
    projects = raw_content.get('projects')
    if projects is None:
        projects = []
    if not isinstance(projects, list):
        return warnings, used
    squash = lambda text: re.sub(r'\s+', '', str(text or '')).casefold()  # noqa: E731
    existing_names = [str(item.get('name') or '').strip() for item in projects if isinstance(item, dict)]
    for proposal in proposals:
        quote = squash(proposal.answer_quote)
        answer = next((a for a in answers if len(quote) >= 10 and quote in squash(a.answer)
                       and not is_none_answer(a.answer)), None)
        if answer is None:
            warnings.append('new_project_quote_not_in_answer')
            continue
        evidence = str(answer.answer)
        compact = squash(evidence)
        name, description = proposal.name.strip(), proposal.description.strip()
        role, tech_stack = proposal.role.strip(), proposal.tech_stack.strip()
        issues = []
        if not name or len(name) > 40 or len(description) < 10:
            issues.append('empty')
        # 영문 낱말(기술 이름)은 모두 답에 있어야 하고, 한글 낱말은 절반 이상이 답에 있어야 한다. 이름은 이름표라
        # 조사·어미를 바꿔 짓는 건 받아 주되, 답에 없는 사실("실시간 추천")을 이름으로 들여오지 못하게 한다.
        tokens = [t for t in re.findall(r'[0-9A-Za-z가-힣+#]{2,}', name) if t.casefold() not in NEW_PROJECT_NAME_GENERIC]
        ascii_tokens = [t for t in tokens if re.fullmatch(r'[0-9A-Za-z+#]+', t)]
        korean_tokens = [t for t in tokens if t not in ascii_tokens]
        korean_hits = sum(t in compact for t in korean_tokens)
        if (not tokens or any(t.casefold() not in compact for t in ascii_tokens)
                or (korean_tokens and korean_hits * 2 < len(korean_tokens))):
            issues.append('name_not_in_answer')
        stack_items = [s.strip() for s in re.split(r'[,/·]', tech_stack) if s.strip()]
        if any(squash(s) not in compact for s in stack_items):
            issues.append('unsupported_term')
        written = f'{name}\n{description}'
        if _unsupported_numbers(written, evidence):
            issues.append('unsupported_number')
        if grounding_terms(written) - grounding_terms(evidence):
            issues.append('unsupported_term')
        if any(term in written and term not in evidence for term in ROLE_EXPANSION_WORDS):
            issues.append('unsupported_role')
        compact_name = squash(name)
        for existing in existing_names:
            existing_tokens = _name_tokens(existing)
            if existing and (SequenceMatcher(None, compact_name, squash(existing)).ratio() >= 0.75
                             or (existing_tokens and all(t in compact_name for t in existing_tokens))):
                issues.append('existing_project')
                break
        path = f'projects[{len(projects)}].description'
        verbatim, notice = _cross_field_overlap(path, '', description, fields)
        if verbatim:
            issues.append('copied_from_other_field')
        if issues:
            warnings.append(f"새 프로젝트 제안을 제외했습니다({','.join(dict.fromkeys(issues))})")
            continue
        if role and squash(role) not in compact:
            role = ''  # 역할은 답에 적힌 말일 때만 채운다. 없으면 사용자가 채운다.
        if stack_items and not [t for t in re.findall(r'[0-9A-Za-z가-힣+#]{2,}', name)
                                if t.casefold() not in PROJECT_FORM_WORDS]:
            # "부트캠프 개인 과제"처럼 형태만 적힌 이름은 무엇을 만든 과제인지 안 보인다(2026-09-15 새 케이스 v16l).
            # 답에 있는 기술 이름과 형태로 다시 짓는다. 사용자는 추가한 뒤 고칠 수 있다.
            name = f"{stack_items[0]} {role or '프로젝트'}"
        # 모델이 같은 답을 질문이 붙어 있던 항목 설명에도 넣었다면 그 수정안은 뺀다. 답이 "그 항목에서는 안 했다"고
        # 한 경험을 기존 항목에 적는 셈이다. 자기소개서처럼 경험을 가리키기만 하는 칸은 그대로 둔다.
        from app.resume_review import _answer_is_reflected
        generation.sentence_reviews = [
            review for review in generation.sentence_reviews
            if not (review.field_path == answer.field_path
                    and EXPERIENCE_DESCRIPTION.fullmatch(review.field_path)
                    and review.suggested_revision
                    and _answer_is_reflected(review.original_quote, review.suggested_revision, description))
        ]
        requirement_id = ((previous_questions or {}).get(answer.question_id) or {}).get('requirement_id')
        generation.sentence_reviews.append(SentenceReview(
            field_path=path,
            original_quote='',
            suggested_revision=description,
            reason=(f"답변에 적은 경험은 이력서에 있는 프로젝트와 다른 경험이라 '{name}' 프로젝트로 새로 추가해요. "
                    '기간은 비워 두니 직접 채워 주세요.'),
            evidence_quotes=[proposal.answer_quote],
            evidence_sources=['answer'],
            status='improved',
            edit_type='content',
            overlap_notice=notice,
            requirement_id=requirement_id,
            new_item=NewResumeItem(question_id=answer.question_id, name=name, role=role,
                                   tech_stack=', '.join(stack_items), description=description),
        ))
        used.add(answer.question_id)
        break
    return warnings, used


def prepare_answers(request, previous, snapshot_hash, refs, fields=None):
    if not request.answers:
        from app.models import ConfirmationAnswer
        if previous and previous.get('input_hash') == snapshot_hash:
            return [ConfirmationAnswer.model_validate(a) for a in previous.get('confirmed_answers', [])]
        return []
    if not previous or request.expected_input_hash != snapshot_hash or previous['input_hash'] != snapshot_hash:
        raise ReviewConflict('resume_version_changed: reload the resume and review')
    known = {q['question_id']: q for q in previous.get('questions', [])}
    answers = []
    seen = set()
    for answer in request.answers:
        question = known.get(answer.question_id)
        if not question or question['field_path'] != answer.field_path or answer.question_id in seen:
            raise ReviewInputError('unknown, duplicate or mismatched question')
        if refs.get(answer.field_path, 'legacy:').startswith('legacy:'):
            raise ReviewConflict('stable_item_id_required')
        if previous.get('item_refs', {}).get(answer.field_path) != refs[answer.field_path]:
            raise ReviewConflict('resume_item_changed')
        if not answer.answer.strip():
            raise ReviewInputError('answer is blank')
        seen.add(answer.question_id)
        field_path = answer.field_path
        if question.get('reason') == MISSING_JOB_TECH_REASON:
            has_no_experience = is_none_answer(answer.answer) or bool(re.search(
                r'(사용\s*경험(?:은|이)?\s*없|경험(?:은|이)?\s*없|해본\s*적\s*없|사용하지\s*않)',
                answer.answer,
            ))
            if not has_no_experience:
                field_path = resolve_missing_technology_project(answer.answer, fields or {})
                if field_path is None and _SEPARATE_WORK.search(answer.answer):
                    # 이력서에 없는 별도 작업("부트캠프 개인 과제로…")이다. 기존 항목 이름이 없는 게 당연하니 되묻지 않고,
                    # 새 프로젝트 제안(add_new_project_proposals)으로 받는다.
                    field_path = answer.field_path
                elif field_path is None:
                    raise ReviewInputError(
                        '어느 항목에서 했는지 확인할 수 없습니다. 프로젝트·경력 등 항목 이름을 함께 적어 주세요.'
                    )
                if refs.get(field_path, 'legacy:').startswith('legacy:'):
                    raise ReviewConflict('stable_item_id_required')
                if previous.get('item_refs', {}).get(field_path) != refs[field_path]:
                    raise ReviewConflict('resume_item_changed')
        elif question.get('requirement_id') and not is_none_answer(answer.answer):
            # 모델이 만든 요건 질문도 답에 다른 항목 이름이 적혀 있으면 그 항목으로 옮긴다. 질문이 붙은 프로젝트 칸에
            # "오프라인 다운로드 프로젝트에서 AVPlayer로…"가 그대로 붙었다(2026-09-15 새 케이스 v16f).
            resolved = resolve_missing_technology_project(answer.answer, fields or {})
            if (resolved and resolved != field_path and not refs.get(resolved, 'legacy:').startswith('legacy:')
                    and previous.get('item_refs', {}).get(resolved) == refs[resolved]):
                field_path = resolved
        answers.append(answer.model_copy(update={
            'field_path': field_path,
            'question': question['question'],
            'answer': normalize_confirmed_answer(answer.answer),
        }))
    # Carry forward previously confirmed facts, but only for an unchanged snapshot.
    from app.models import ConfirmationAnswer
    prior = [ConfirmationAnswer.model_validate(a) for a in previous.get('confirmed_answers', []) if a.get('question_id') not in seen]
    return prior + answers


def normalize_diagnostics(generation, fields, has_job, previous):
    by_key = {d.criterion: d for d in generation.diagnostics}
    for criterion in CRITERIA:
        d = by_key.get(criterion)
        if d is None or any(p not in fields for p in d.field_paths) or (criterion in ('company_fit', 'relevance') and not has_job):
            by_key[criterion] = Diagnostic(criterion=criterion, status='not_evaluated', reason='평가에 필요한 근거 또는 공고가 없습니다.')
        elif d.status == 'issue' and not d.field_paths:
            d.status = 'not_evaluated'
            d.reason = '문제 위치를 확인하지 못했습니다.'
    generation.diagnostics = [by_key[k] for k in CRITERIA]
    generation.star_checks = [s for s in generation.star_checks if s.field_path in fields]
    changes = {'resolved': [], 'unresolved': [], 'new': [], 'not_evaluated': []}
    if previous:
        old = {d['criterion']: d['status'] for d in previous.get('diagnostics', [])}
        for d in generation.diagnostics:
            if d.status == 'not_evaluated':
                changes['not_evaluated'].append(d.criterion)
            elif d.status == 'issue':
                changes['unresolved' if old.get(d.criterion) == 'issue' else 'new'].append(d.criterion)
            elif old.get(d.criterion) == 'issue':
                changes['resolved'].append(d.criterion)
    return changes


_NONE_ANSWER = re.compile(
    r'^\s*(?:없음|없어요|없습니다|해당\s*(?:경험\s*)?없음|(?:그런\s*)?경험(?:은|이)?\s*없(?:음|어요|습니다)|'
    r'(?:잘\s*)?모르겠(?:어요|습니다)|기억(?:이\s*)?나지\s*않(?:아요|습니다)|넘어갈게요)\s*[.!]?\s*$'
)


def uncertain_scope_note(answers) -> str:
    """이번 답에서 확신하지 못한 문장을 모델에 짚어 준다. 없으면 빈 문자열."""
    sentences = [sentence for answer in answers for sentence in split_uncertain_answer(answer.answer)[1]]
    if not sentences:
        return ''
    return ' 이번 답에서 확신하지 못한 문장: ' + ' / '.join(f"'{sentence}'" for sentence in sentences[:6])


def is_none_answer(text):
    """앱의 "없음" 카드나 그만큼 짧은 부정 답. 사실이 섞인 답("pyserial로 작성했고 시간은 안 쟀어요")은 아니다."""
    return bool(_NONE_ANSWER.match(str(text or '')))


_EMPTY_QUESTION = re.compile(r'^\s*(?:없음|없습니다|해당\s*없음|null|none|n/?a|-)\s*[.]?\s*$', re.IGNORECASE)


def is_empty_question(text):
    """모델이 '질문 없음'을 질문 칸에 글자로 적어 보낸 경우. 그대로 두면 앱에 "없음"이 질문으로 뜬다."""
    return not str(text or '').strip() or bool(_EMPTY_QUESTION.match(str(text)))


def _similar_question(text_key, accepted_keys):
    """같은 경험에 거의 같은 문장으로 두 번 묻는 질문을 가린다.

    주제(topic)가 달라도 "직접 수행한 작업은?"과 "직접 수행한 작업과 그 결과는?"은 같은 질문이다.
    """
    # 2026-09-14 실제 첨삭 결과로 잰 값: 같은 질문 0.58~0.61, 다른 질문 0.14~0.55.
    return any(SequenceMatcher(None, text_key, other).ratio() >= 0.57 for other in accepted_keys)


def normalize_questions(generation, fields, answers, review_id):
    candidates = list(generation.questions)
    for sentence in generation.sentence_reviews:
        if is_empty_question(sentence.confirmation_question):
            sentence.confirmation_question = None
        if sentence.confirmation_question:
            candidates.append(ReviewQuestion(field_path=sentence.field_path, topic='other', question=sentence.confirmation_question, reason=sentence.reason))
    answered = {(a.field_path, re.sub(r'\W', '', a.question)) for a in answers}
    # 답한 질문을 표현만 바꿔 다시 묻지 않는다. 글자가 같을 때만 거르면 재첨삭마다 모델이 같은 뜻의
    # 질문을 새 문장으로 내서, 같은 프로젝트를 세 번 묻는 대화가 나왔다(2026-09-15 목업 첨삭).
    accepted_text = {}
    for a in answers:
        accepted_text.setdefault(group(a.field_path), []).append(re.sub(r'\W', '', a.question))
    seen = set()
    questions = []
    for q in sorted(candidates, key=lambda q: q.priority):
        text_key = re.sub(r'\W', '', q.question)
        if q.requirement_id:
            # 요건마다 질문 하나. "Kafka 써봤나요?"와 "Linux 써봤나요?"는 문장 틀이 같아도 다른 질문이다.
            key = ('requirement', q.requirement_id)
        else:
            key = (group(q.field_path), q.topic) if q.topic != 'other' else (group(q.field_path), text_key)
        if q.field_path not in fields or is_empty_question(q.question) or key in seen or (q.field_path, text_key) in answered:
            continue
        if not q.requirement_id and _similar_question(text_key, accepted_text.get(group(q.field_path), [])):
            continue
        accepted_text.setdefault(group(q.field_path), []).append(text_key)
        seen.add(key)
        q.question_id = digest([review_id, q.field_path, q.topic, text_key])[:24]
        questions.append(q)
    generation.questions = questions[:30]
    generation.confirmation_questions = [q.question for q in generation.questions[:3]]


def carry_forward_unanswered_questions(generation, previous, answers):
    """Reissue queued questions on the latest review snapshot.

    The chat can continue through questions returned by the first review while
    each accepted edit rebases the resume.  Reissuing unanswered questions
    gives them a new question_id owned by the latest review, so the next
    answer is verifiable instead of being rejected as stale.
    """
    if not previous:
        return
    answered_ids = {answer.question_id for answer in answers}
    known = {
        (question.field_path, question.topic, re.sub(r'\W', '', question.question))
        for question in generation.questions
    }
    for raw_question in previous.get('questions', []):
        if raw_question.get('question_id') in answered_ids:
            continue
        question = ReviewQuestion.model_validate(raw_question)
        key = (question.field_path, question.topic, re.sub(r'\W', '', question.question))
        if key in known:
            continue
        generation.questions.append(question.model_copy(update={'question_id': ''}))
        known.add(key)


THIN_SELF_INTRO_MIN_CHARS = 200
MAX_THIN_QUESTIONS_JOB = 2


def add_thin_self_introduction_questions(generation, fields, star_checks=None, job_review=False):
    """Guarantee follow-up for self-introduction answers with too little detail.

    A model can return one strong project question and miss several thin
    자기소개서 문항.  Those fields must not silently turn the whole review into
    "complete".  We add grounded, fact-seeking questions only for non-empty
    bodies that the model did not already target.  A self-introduction answer
    needs more room than a project bullet to explain its context and evidence.
    """
    existing_paths = {question.field_path for question in generation.questions}
    stars = star_by_path(star_checks or [])
    followups = []
    for path, body in fields.items():
        if not re.fullmatch(r'selfIntroduction\.[^.]+\.body', path):
            continue
        if job_review and not STAR_TARGET.fullmatch(path):
            # 공고 맞춤 첨삭의 지원동기·입사 후 포부는 공고 업무와 연결하는 질문이 따로 있다. "직접 한 행동을 더
            # 알려 주세요"는 그 문항에 맞지 않아(2026-09-15 목업: 틀 질문 6개 중 4개가 지원동기) 경험 문항에만 붙인다.
            continue
        if len(re.sub(r'\s+', '', body)) >= THIN_SELF_INTRO_MIN_CHARS or path in existing_paths:
            continue
        # 길이만 보면 짧지만 행동과 결과가 이미 적힌 문항("로그를 모아 원인을 찾아 실패율을 0으로")에도 "직접 한
        # 행동을 더 알려 주세요"를 붙였다(2026-09-15). STAR 판정에서 행동·결과가 모두 있으면 묻지 않는다.
        if has_elements(stars.get(path), 'action', 'result'):
            continue
        section = path.split('.')[1]
        label = {
            'intro': '자기소개',
            'motivation': '지원동기',
            'challenge': '어려움 극복 경험',
            'growth': '성장과정',
            'strengthsWeaknesses': '성격의 장단점',
            'aspiration': '입사 후 포부',
        }.get(section, '자기소개서')
        followups.append(ReviewQuestion(
            field_path=path,
            topic='action',
            question=(
                f'{label} 문항에서 본인이 직접 한 행동이나 경험을 조금 더 '
                '구체적으로 알려 주세요. 결과·배운 점이 있다면 함께 적어 주세요.'
            ),
            reason='문항 내용이 충분하지 않아 경험의 근거와 직무 연관성을 확인하기 어렵습니다.',
            priority=3,
        ))
        existing_paths.add(path)
    if job_review:
        # 공고 맞춤 첨삭은 요건·경험 질문이 먼저다. 문항마다 같은 문장인 틀 질문은 두 개까지만 붙인다.
        followups = followups[:MAX_THIN_QUESTIONS_JOB]
    # 문항마다 같은 문장으로 묻는 질문이라 모델 질문 뒤에 둔다. 예전에는 맨 앞(priority 1)에
    # 넣어, 앱이 보여주는 질문 7개 중 4~5개를 이 질문이 차지하고 공고 요건·프로젝트 질문이
    # 밀려났다(2026-09-14 개발용 목업 첨삭).
    generation.questions = generation.questions + followups


def add_missing_job_technology_question(generation, fields, job_text):
    """Turn a selected posting's missing technical evidence into one question.

    Job text is never evidence that the applicant has a skill.  This only asks
    whether an omitted, real experience exists, before any tailored revision
    may use it.
    """
    job_terms = technology_mentions(job_text or '')
    resume_terms = technology_mentions('\n'.join(fields.values()))
    missing_terms = sorted(job_terms - resume_terms, key=str.casefold)
    if not missing_terms:
        return
    if any(question.reason.startswith('공고에 언급된 기술') for question in generation.questions):
        return
    targets = _item_description_targets(fields)
    if not targets:
        return
    target_path = targets[0][0]  # Transport path only; the answer reroutes it.
    named_terms = ', '.join(missing_terms[:3])
    generation.questions.insert(0, ReviewQuestion(
        field_path=target_path,
        topic='scope',
        question=(
            f'선택 공고에 언급된 {named_terms}을(를) 실제로 사용해 본 적이 있나요? 있다면 이력서의 어느 '
            '항목(프로젝트·경력 등)에서 무엇을 직접 했는지 항목 이름과 함께 알려 주세요. '
            '사용 경험이 없다면 없다고 답해 주세요.'
        ),
        reason=MISSING_JOB_TECH_REASON,
        priority=1,
    ))


def item_display_name(fields, path):
    """질문에 넣을 항목 이름. "'LMS 출결 관리 서비스' 프로젝트", "'(주)예시커머스' 경력".

    "이 프로젝트에서 해결하려던 문제는?"처럼 이름 없이 물으면 사용자는 어느 프로젝트인지 몰라 다른 프로젝트
    이야기를 답하고, 답이 항목과 맞지 않아 수정안이 나오지 않는다(2026-09-15 목업: 반영 실패 7건 중 5건).
    """
    match = EXPERIENCE_ITEM.match(path)
    if not match:
        return ''
    section, index = match.group(1), match.group(2)
    name_key = {'projects': 'name', 'experience': 'company', 'awards': 'name',
                'otherActivities': 'name', 'trainingExperience': 'course'}[section]
    suffix = {'projects': '프로젝트', 'experience': '경력', 'awards': '수상', 'otherActivities': '활동',
              'trainingExperience': '교육'}[section]
    name = str(fields.get(f'{section}[{index}].{name_key}') or '').strip()
    return f"'{name}' {suffix}" if name else f'{int(index) + 1}번 {suffix}'


def prefer_project_evidence_over_surface_edit(generation, fields, answers, star_checks=None):
    """한 줄짜리 프로젝트 설명을 다듬은 수정안에 문제·담당 범위·결과 질문을 함께 붙인다.

    문장만 매끄럽게 해서는 지원 근거가 강해지지 않으므로 질문으로 사실을 더 받는다. 다만 다듬은
    문장 자체는 지우지 않는다(사용자가 고르게 둔다).
    """
    answered_paths = {
        answer.field_path for answer in answers if str(answer.answer).strip()
    }
    questioned_paths = {question.field_path for question in generation.questions}
    stars = star_by_path(star_checks or [])
    for review in generation.sentence_reviews:
        path = review.field_path
        original = fields.get(path, '')
        is_short_project_description = (
            bool(re.fullmatch(r'projects\[\d+\]\.description', path)) and
            len(re.sub(r'\s+', '', original)) < 160
        )
        is_surface_edit = review.edit_type in {'spelling', 'tone', 'clarity'}
        if (
            not is_short_project_description or
            not is_surface_edit or
            not review.suggested_revision or
            path in answered_paths
        ):
            continue
        # 예전에는 이 수정안을 지우고 질문만 남겼다. 그러면 한 줄짜리 프로젝트 설명이 많은 이력서는
        # 자동 수정안이 거의 나오지 않았다(2026-09-15 목업: 첫 첨삭 수정안 26개 중 6개가 여기서 사라짐).
        # 다듬은 문장은 그대로 보여 주고, 문제·담당 범위·결과 질문을 함께 붙인다.
        if has_elements(stars.get(path), 'action', 'result'):
            continue  # 행동·결과가 이미 적힌 설명("N+1 제거로 p95 1.2s→0.5s")은 파고들지 않는다.
        if path not in questioned_paths and not review.confirmation_question:
            target = item_display_name(fields, path) or '이 프로젝트'
            review.confirmation_question = (
                f'{target}에서 해결하려던 기존 문제와 본인이 맡은 구현 범위, '
                '확인한 결과를 알려 주세요.'
            )
            questioned_paths.add(path)


# 모델이 요건과 연결하지 않고 직접 묻는 지원 조건 질문. "6개월 풀타임 근무가 가능한가요?", "지원 지역이 어디인가요?"
# (2026-09-14 A/B에서 진단을 넣든 빼든 나왔다). 답해도 이력서에 적을 문장이 없다.
_ELIGIBILITY_QUESTION = re.compile(
    r'(근무(?:가|를|는)?\s*가능|근무\s*형태|풀타임|출근\s*가능|입사\s*가능|지원\s*지역|거주\s*지|병역|군\s*복무|'
    r'경력(?:으로)?\s*인정|(?:경력|경험)\s*(?:기간|연수)[^?]*(?:이하|이상|넘)|\d+\s*년\s*(?:이하|이상)인지)'
)
# 사용자에게 보이는 문장에 새어 나온 내부 이름. "coreCompetencies.text 필드", "field_path 기준으로".
# 한글 조사가 바로 붙으므로("description의") \b 대신 영문·숫자 경계를 쓴다.
_INTERNAL_PATH = re.compile(
    r'(?<![A-Za-z0-9_])(?:coreCompetencies|selfIntroduction|trainingExperience|otherActivities|techStack|projects|'
    r'experience|awards|certifications|education|basicInfo)(?:\[\d+\])?(?:\.[A-Za-z]+)+(?![A-Za-z0-9_])'
)
_INTERNAL_WORD = re.compile(
    r'(?<![A-Za-z0-9_])(?:field_path|requirement_id|edit_type|sentence_reviews|original_quote|evidence_quotes)'
    r'(?![A-Za-z0-9_])|필드\s*경로'
)
def humanize_internal_terms(text, fields):
    """내부 경로·필드 이름을 사용자가 아는 이름으로 바꾼다."""
    if not text:
        return text

    def path_name(match):
        path = match.group(0)
        name = item_display_name(fields, path)
        if name:
            return name
        return SECTION_NAMES.get(re.match(r'[A-Za-z]+', path).group(0), '이력서 항목')

    text = _INTERNAL_PATH.sub(path_name, text)
    return _INTERNAL_WORD.sub('항목', text)


def filter_questions_by_resume_facts(generation, fields, star_checks):
    """답해도 이력서에 적을 게 없거나 이미 적힌 것을 묻는 질문을 거르고, 보이는 문장의 내부 용어를 바꾼다.

    - 요건과 연결되지 않은 지원 조건 질문(근무 가능 여부·지역·경력 인정)은 버린다.
    - 요건과 연결되지 않은 경험 질문 중, 묻는 요소(topic)가 이미 원문에 있는 것은 버린다. "결과는 무엇이었나요?"를
      "240ms→80ms"가 적힌 항목에 묻지 않는다.
    """
    stars = star_by_path(star_checks or [])
    targets = _item_description_targets(fields)
    kept = []
    for question in generation.questions:
        question.question = humanize_internal_terms(question.question, fields)
        question.reason = humanize_internal_terms(question.reason, fields)
        # 이름·역할·기술 스택 이름 같은 짧은 칸에 붙은 질문. 답이 그 칸으로 가면 문장이 될 수 없어 보류되고, 같은 칸에
        # 확인 질문이 이어져 세 턴이 헛돌았다(2026-09-15 새 케이스 v16e). 항목 설명 칸으로 옮기고, 기술 스택 질문은
        # 답에 적힌 항목 이름으로 옮기는 경로(MISSING_JOB_TECH_REASON)를 탄다.
        nominal = re.fullmatch(
            rf'(?:techStack\[\d+\]\.(?:name|level))|((?:{EXPERIENCE_SECTION_PATTERN})\[\d+\])'
            r'\.(?:name|company|role|course|organization|techStack)', question.field_path)
        if nominal:
            item_description = f'{nominal.group(1)}.description' if nominal.group(1) else None
            if item_description in fields:
                question.field_path = item_description
            elif targets:
                question.field_path = targets[0][0]
                question.reason = MISSING_JOB_TECH_REASON
            else:
                continue
        if not question.requirement_id and _ELIGIBILITY_QUESTION.search(question.question):
            continue
        check = stars.get(question.field_path)
        if not question.requirement_id and (
            (question.topic in STAR_LABELS and has_elements(check, question.topic))
            # 행동과 결과가 모두 적힌 항목은 topic이 other·scope여도 더 파고들지 않는다. "○○ 외에 추가로 확인한 결과가
            # 있나요?"가 topic=other로 와서 거르기를 빠져나갔다(2026-09-15 새 케이스 v16f).
            or (has_elements(check, 'action', 'result') and STAR_TARGET.fullmatch(question.field_path))
        ):
            continue
        kept.append(question)
    generation.questions = kept
    for review in generation.sentence_reviews:
        review.reason = humanize_internal_terms(review.reason, fields)
        if review.confirmation_question:
            review.confirmation_question = humanize_internal_terms(review.confirmation_question, fields)
    generation.summary = humanize_internal_terms(generation.summary, fields)


REQUIREMENT_QUESTION_REASON = '공고 요건과 관련된 실제 경험이 있는지 확인합니다.'
MAX_REQUIREMENT_QUESTIONS = 4


def add_requirement_questions(generation, fields, requirement_rows, max_preferred=2):
    """근거를 찾지 못한 공고 요건마다 질문이 하나씩 있게 한다.

    모델이 요건 질문을 빠뜨리면 사용자는 공고와 무엇이 맞지 않는지 모른 채 문장 수정만 받는다.
    필수 요건은 모두, 우대 요건은 두 개까지 묻는다. 기술 요건은 어느 프로젝트에서 썼는지 답하게 해
    그 프로젝트 항목으로 답을 옮긴다(MISSING_JOB_TECH_REASON 경로).
    """
    asked = {q.requirement_id for q in generation.questions if q.requirement_id}
    targets = _item_description_targets(fields)
    preferred_added = 0
    for row in requirement_rows:
        if row['status'] not in {'unconfirmed', 'partial'} or row['group'] == 'task' or row['id'] in asked:
            continue
        if row.get('kind') == 'eligibility':
            continue  # 경력 연수·학력·면허·근무 조건은 이력서 문장으로 고칠 게 없다. 표에 "확인만"으로 둔다.
        if row['group'] == 'preferred':
            if preferred_added >= max_preferred:
                continue
            preferred_added += 1
        label = row['label']
        kind = '필수' if row['group'] == 'must' else '우대'
        is_technology = bool(technology_mentions(label) or re.search(r'[A-Za-z]', label))
        # 일부 근거가 기술 스택 이름 같은 짧은 칸에만 있으면("Fastlane") 그 칸에 질문을 붙이지 않는다. 답이 그 칸을 문장으로
        # 덮어썼다(2026-09-15 새 케이스). 설명 칸이 아니면 아래 기술 요건 질문으로 내려가 답의 항목 이름으로 옮긴다.
        narrative_evidence = [p for p in row.get('evidence_paths') or []
                              if EXPERIENCE_DESCRIPTION.fullmatch(p) or p == 'coreCompetencies.text']
        if row['status'] == 'partial' and narrative_evidence:
            path = narrative_evidence[0]
            where = item_display_name(fields, path)
            question = (f"공고 {kind} 요건인 '{label}'은(는) 이력서에 일부만 드러나 있어요. "
                        f"{where + '에서 ' if where else ''}직접 한 일을 조금 더 알려 주세요. "
                        '해 본 적이 없다면 없다고 답해 주세요.')
            reason = REQUIREMENT_QUESTION_REASON
        elif is_technology and targets:
            # 특정 항목을 지목하면("'산업체 현장실습'에서 써 봤나요?") 그 항목 이야기로만 답하게 된다. 어느 항목인지는
            # 사용자가 고르게 하고, 답에 적힌 항목 이름으로 옮긴다(resolve_missing_technology_project).
            path = targets[0][0]
            question = (f"공고 {kind} 요건인 '{label}'을(를) 실제로 써 본 적이 있나요? 있다면 이력서의 어느 항목"
                        '(프로젝트·경력 등)에서 무엇을 직접 했는지 항목 이름과 함께 알려 주세요. 없다면 없다고 답해 주세요.')
            reason = MISSING_JOB_TECH_REASON
        else:
            path = 'coreCompetencies.text' if 'coreCompetencies.text' in fields else next(iter(fields), '')
            question = (f"공고 {kind} 요건인 '{label}'과(와) 관련된 실제 경험이 있나요? 있다면 어디서 무엇을 "
                        '직접 했는지 알려 주세요. 없다면 없다고 답해 주세요.')
            reason = REQUIREMENT_QUESTION_REASON
        if not path:
            continue
        generation.questions.append(ReviewQuestion(
            field_path=path, topic='scope', question=question, reason=reason,
            priority=1 if row['group'] == 'must' else 2, requirement_id=row['id'],
        ))
        asked.add(row['id'])


def _review_stage(field_path, requirement_id=None, edit_type=None):
    """대화 단계: 1 문장 다듬기 · 2 공고 요건 확인 · 3 경험 보완 · 4 지원동기 · 5 자기소개서.

    모델에게 순서를 맡기면 첨삭마다 달라진다. 앱이 단계 줄을 그리려면 서버가 고정해야 한다.
    문장 다듬기(새 사실 없는 표현 수정)는 앱이 한 카드로 묶어 먼저 한 번에 적용하게 하고, 그 뒤에
    질문으로 사실을 받는다. 답변 재첨삭은 적용된 최신 문장 위에서 이어진다.
    """
    if edit_type in {'spelling', 'tone', 'clarity'}:
        return 1
    if requirement_id:
        return 2
    if field_path.startswith('selfIntroduction.motivation'):
        return 4
    if field_path.startswith('selfIntroduction'):
        return 5
    return 3


def assign_review_stages(generation, requirement_rows):
    """질문·수정안에 단계를 매기고, 질문을 단계 → 중요도 순으로 세운다."""
    open_ids = {row['id'] for row in requirement_rows if row['status'] in {'unconfirmed', 'partial'}}
    known_ids = {row['id'] for row in requirement_rows}
    rows_by_id = {row['id']: row for row in requirement_rows}
    requirement_reasons = {REQUIREMENT_QUESTION_REASON, MISSING_JOB_TECH_REASON}
    kept = []
    for question in generation.questions:
        if question.requirement_id and question.requirement_id not in known_ids:
            question.requirement_id = None
        row = rows_by_id.get(question.requirement_id) if question.requirement_id else None
        if row is not None and row.get('kind') == 'eligibility':
            continue  # 지원 자격에 붙은 질문은 답해도 이력서에 적을 게 없다.
        if row is not None and row.get('group') == 'task' and row.get('status') == 'unconfirmed':
            # 주요 업무는 이력서에 비슷한 경험이 있을 때(partial)만 묻는다. 근거가 전혀 없는 업무를 물으면
            # "그런 경험은 없어요"만 쌓인다.
            continue
        if question.requirement_id and question.requirement_id not in open_ids:
            if question.reason in requirement_reasons:
                continue  # 요건을 확인하려던 질문인데 이미 확인됐거나 없다고 답했다.
            # 모델이 경험 질문("주문 조회 개선에서 직접 한 일은?")을 이미 충족된 요건에 붙인 경우다.
            # 버리면 경험 보완 질문이 통째로 사라진다(2026-09-15 목업: 26개 → 4개). 요건 연결만 끊는다.
            question.requirement_id = None
        question.stage = _review_stage(question.field_path, question.requirement_id)
        kept.append(question)
    # 요건 질문은 한 번에 MAX_REQUIREMENT_QUESTIONS개까지. 공고 요건만 여섯 번 묻다 보면 경험 보완·문장
    # 다듬기에 닿기 전에 사용자가 지친다(2026-09-15 목업: 첫 7개 질문 중 36/56이 요건 질문). 필수 → 우대 →
    # 주요 업무 순으로 남기고, 넘치는 것 중 서버가 만든 요건 질문은 버리고 모델의 질문은 경험 질문으로 돌린다.
    group_order = {row['id']: {'must': 0, 'preferred': 1}.get(row.get('group'), 2) for row in requirement_rows}
    linked = sorted((q for q in kept if q.requirement_id), key=lambda q: (group_order.get(q.requirement_id, 3), q.priority))
    overflow = {id(q) for q in linked[MAX_REQUIREMENT_QUESTIONS:]}
    capped = []
    for question in kept:
        if id(question) in overflow:
            if question.reason in requirement_reasons:
                continue
            question.requirement_id = None
            question.stage = _review_stage(question.field_path)
        capped.append(question)
    kept = capped
    kept.sort(key=lambda q: (q.stage, group_order.get(q.requirement_id, 3) if q.requirement_id else 0, q.priority))
    generation.questions = kept
    generation.confirmation_questions = [q.question for q in kept[:3]]
    for item in generation.sentence_reviews:
        if item.requirement_id and item.requirement_id not in known_ids:
            item.requirement_id = None
        item.stage = _review_stage(item.field_path, item.requirement_id, item.edit_type)


def run_review(service, id_token, request):
    # Import here to keep pure helpers independent of model/provider construction.
    from app.fact_check import check_and_repair_revisions
    from app.resume_review import (
        add_flow_notices,
        add_pending_repeated_fact_notices,
        add_substantive_answer_fallback,
        extract_review_fields,
        enforce_resume_review_grounding,
        ground_sentences,
        require_answer_reflection,
    )
    db = service._firebase
    uid = db.verify_id_token(id_token)
    if request.tailored_resume_id and request.review_mode != 'job':
        raise ReviewInputError('tailored_resume_requires_job_review')
    if request.tailored_resume_id:
        resume = db.get_owned_tailored_resume(
            request.cohort_id,
            request.resume_id,
            request.tailored_resume_id,
            uid,
        )
    else:
        resume = db.get_owned_resume(request.cohort_id, request.resume_id, uid)
    raw_content = resume.get('content') or {}
    fields, excluded = extract_review_fields(raw_content)
    refs = item_references(raw_content, fields)
    snapshot_hash = digest(raw_content)
    time_context = project_time_context(raw_content)
    fields = {key: redact(value) for key, value in fields.items()}
    if not fields or not any(len(v.strip()) >= 3 for v in fields.values()):
        raise ReviewInputError('resume is empty')
    text = json.dumps(fields, ensure_ascii=False)
    if len(text) > 50000:
        raise ReviewInputError('resume exceeds 50000 characters')
    previous = None
    if request.previous_review_id:
        if request.tailored_resume_id:
            previous = db.get_ai_review(
                request.cohort_id,
                request.resume_id,
                uid,
                request.previous_review_id,
                request.tailored_resume_id,
            )
        else:
            previous = db.get_ai_review(
                request.cohort_id, request.resume_id, uid, request.previous_review_id
            )
    is_gap_audit = request.review_phase == 'gap_audit'
    if is_gap_audit and (previous is None or request.answers):
        raise ReviewInputError('gap_audit_requires_previous_review_without_answers')
    if request.expected_input_hash and request.expected_input_hash != snapshot_hash:
        raise ReviewConflict('resume_version_changed')
    job_source = {}
    job_conditions = {}
    job_text = request.job_posting_text
    if request.review_mode == 'general' and (request.selected_job_id or job_text):
        raise ReviewInputError('general_review_cannot_include_job')
    if request.selected_job_id:
        from app.matching_handoff import load_selected_job
        if request.job_posting_text:
            raise ReviewInputError('selected_job_and_client_text_are_mutually_exclusive')
        job = load_selected_job(service._settings.matching_job_store_path, request.selected_job_id)
        job_source, job_text = job['source'], job['text']
        job_conditions = job.get('conditions') or {}
        if request.expected_job_hash and request.expected_job_hash != job_source['snapshot_hash']:
            raise ReviewConflict('selected_job_changed')
        if request.tailored_resume_id and resume.get('jobId') != request.selected_job_id:
            raise ReviewConflict('tailored_resume_job_mismatch')
        if request.tailored_resume_id and resume.get('jobSnapshotHash') != job_source['snapshot_hash']:
            raise ReviewConflict('tailored_resume_job_changed')
    elif request.tailored_resume_id:
        raise ReviewInputError('tailored_resume_requires_selected_job')
    answers = prepare_answers(request, previous, snapshot_hash, refs, fields)
    if len(answers) > 30:
        raise ReviewInputError('too many accumulated answers')
    current_answer_ids = {answer.question_id for answer in request.answers}
    current_answers = [answer for answer in answers if answer.question_id in current_answer_ids]
    # 답에 이름이 나온 다른 경험 항목도 이번 재첨삭에서 고칠 수 있게 한다(저장하지 않는다).
    mentioned_answers = (
        [] if is_gap_audit else mentioned_item_answers(current_answers, fields, refs, previous)
    )
    # 떼어 낸 문장은 질문한 칸의 근거에서 뺀다(저장하는 답은 그대로).
    evidence_answers = without_mentioned_sentences(answers, mentioned_answers, fields) + mentioned_answers
    turn_answers = without_mentioned_sentences(current_answers, mentioned_answers, fields) + mentioned_answers
    prompt_fields, prompt_answers, is_focused_followup = focused_followup_context(
        fields, evidence_answers, current_answers + mentioned_answers,
    )
    prompt_resume_text = json.dumps(prompt_fields, ensure_ascii=False)
    prompt_job_text = (
        followup_job_prompt_text(job_text, job_source)
        if is_focused_followup
        else review_job_prompt_text(job_text, job_source)
    )
    prompt_time_context = (
        focused_time_context(time_context, current_answers)
        if is_focused_followup
        else time_context
    )
    fingerprint = digest([uid, request.model_dump(), snapshot_hash, job_source, PROMPT_VERSION])
    if request.tailored_resume_id:
        state = db.claim_review(
            request.cohort_id,
            request.resume_id,
            uid,
            request.request_id,
            fingerprint,
            request.tailored_resume_id,
        )
    else:
        state = db.claim_review(
            request.cohort_id, request.resume_id, uid, request.request_id, fingerprint
        )
    if state.get('response'):
        return FirestoreResumeReviewResponse.model_validate(state['response'])
    telemetry = {'model': service._settings.openai_model, 'prompt_version': PROMPT_VERSION,
                 'input_tokens': None, 'output_tokens': None, 'elapsed_ms': None, 'status': 'processing'}
    started = time.monotonic()
    # "없음" 카드처럼 답 전체가 경험 없음·모름이면 모델을 부르지 않는다. 고칠 사실이 없는데 재첨삭을
    # 한 번 돌리면 사용자는 10초를 기다리고, 모델이 그 답으로 문장을 만들 위험만 생긴다. 답은 그대로
    # 기록해 두어 누락 점검이 같은 것을 다시 묻지 않게 한다.
    skip_model = bool(current_answers) and not is_gap_audit and all(
        is_none_answer(answer.answer) for answer in current_answers
    )
    # 공고 요건 표. 첫 첨삭은 공고당 한 번 정리해 둔 요건을 쓰고, 후속·누락 점검은 이전 표를 이어받는다.
    previous_rows = list((previous or {}).get('requirement_map') or [])
    previous_questions = {q.get('question_id'): q for q in (previous or {}).get('questions', [])}
    answered_requirement_ids = {
        previous_questions.get(answer.question_id, {}).get('requirement_id') for answer in current_answers
    } - {None}
    requirements = []
    if request.review_mode == 'job' and job_text:
        if previous_rows:
            requirements = [JobRequirement(id=row['id'], group=row['group'], label=row['label'],
                                           posting_quote=row['posting_quote']) for row in previous_rows]
        elif not is_focused_followup and not is_gap_audit:
            requirement_started = time.monotonic()
            try:
                requirements = load_or_extract_requirements(
                    db, getattr(service, '_requirement_extractor', None), job_text, job_source,
                )
            except Exception as exc:  # noqa: BLE001 — 요건 정리가 실패해도 문장 첨삭은 한다
                telemetry['requirements_error'] = type(exc).__name__
            telemetry['requirements_ms'] = round((time.monotonic() - requirement_started) * 1000)
    requirements = classify_requirements(requirements, job_conditions)
    prompt_requirements = requirements
    if is_focused_followup:
        prompt_requirements = [r for r in requirements if r.id in answered_requirement_ids]
    # 명사형으로 끊긴 문장은 첫 첨삭에서만 목록으로 준다(후속 첨삭은 답한 항목만 고친다).
    fragment_targets = noun_fragment_targets(prompt_fields) if not is_focused_followup and not is_gap_audit else []
    try:
        generated = ResumeReviewGeneration(
            summary=str((previous or {}).get('summary') or ''), section_reviews=[],
        ) if skip_model else service._generator({
            'resume_text': prompt_resume_text,
            'confirmed_answers': json.dumps(
                [a.model_dump(exclude={'question_id'}) for a in prompt_answers], ensure_ascii=False,
            ),
            'current_turn_answers': json.dumps(
                [a.model_dump(exclude={'question_id'}) for a in turn_answers],
                ensure_ascii=False,
            ),
            'job_posting_text': redact(prompt_job_text),
            'job_requirements': requirements_prompt_text(prompt_requirements),
            # STAR는 첫 첨삭에서만 모델이 판정한다. 후속 첨삭마다 다시 받으면 재첨삭이 3.5초 느려졌다(2026-09-15 목업).
            'star_targets': json.dumps(
                star_targets(prompt_fields) if not is_gap_audit and not is_focused_followup else [],
                ensure_ascii=False,
            ),
            'noun_fragments': json.dumps(fragment_targets, ensure_ascii=False),
            'resume_time_context': prompt_time_context,
            'review_scope': (
                '누락 점검 단계입니다. 기존 첨삭을 다시 쓰거나 수정안을 만들지 마세요. '
                '확인된 답변을 존중하고, 아직 확인되지 않은 중요한 사실만 새로운 질문으로 만드세요.'
                if is_gap_audit
                else (
                    '첫 검토입니다. 이력서 전체와 선택 공고를 비교해 검토하세요.'
                    if not is_focused_followup
                    else '후속 첨삭입니다. 이번 답변의 field_path와 같은 이력서 항목만 수정하세요. '
                    '다른 항목의 새 진단·수정·질문은 만들지 마세요. ' + MIXED_ANSWER_RULE + ' ' + UNCERTAIN_ANSWER_RULE
                    + uncertain_scope_note(turn_answers) + ' ' + ANSWER_FLOW_RULE + ' ' + NEW_PROJECT_RULE
                )
            ),
            'review_mode': (
                '일반 이력서 첨삭 — 공고 없이 문장·경험·역할·성과 근거를 검토'
                if request.review_mode == 'general'
                else '공고 맞춤 첨삭 — 선택 공고와 이력서 원문을 비교'
            ),
            'review_focus': redact(request.review_focus or '전체 검토'),
            # 후속 첨삭만 새 프로젝트 제안 칸이 있는 출력 스키마를 쓴다. 생성기가 프롬프트에 넣기 전에 뺀다.
            'allow_new_projects': is_focused_followup and not is_gap_audit,
        })
        if skip_model:
            telemetry.update(input_tokens=0, output_tokens=0, model_skipped='none_answer')
        # Structured output with include_raw preserves usage without logging content.
        if isinstance(generated, dict) and 'parsed' in generated:
            raw = generated.get('raw')
            usage = getattr(raw, 'usage_metadata', None) or {}
            telemetry.update(input_tokens=usage.get('input_tokens'), output_tokens=usage.get('output_tokens'))
            if generated.get('parsing_error') or generated.get('parsed') is None:
                raise RuntimeError('invalid structured model response')
            generated = generated['parsed']
        if is_gap_audit:
            # A final audit may discover questions only. It must never replace
            # an already accepted edit with a different model rewrite.
            generated.sentence_reviews = []
            for section in generated.section_reviews:
                section.suggested_revision = None
        grounded, warnings = enforce_resume_review_grounding('\n'.join(fields.values()), generated)
        warnings.extend(ground_sentences(fields, evidence_answers, grounded, job_text or ""))
        warnings.extend(require_answer_reflection(grounded, turn_answers))
        new_project_reviews = []
        if not is_gap_audit and is_focused_followup:
            project_warnings, new_project_answer_ids = add_new_project_proposals(
                grounded, fields, raw_content, current_answers, previous_questions,
            )
            warnings.extend(project_warnings)
            # 새 항목 수정안은 기존 칸의 원문 위치가 없어 아래 재검증(ground_sentences)을 통과할 수 없다. 따로 두었다 붙인다.
            new_project_reviews = [review for review in grounded.sentence_reviews if review.new_item is not None]
            grounded.sentence_reviews = [review for review in grounded.sentence_reviews if review.new_item is None]
        else:
            grounded.new_projects = []
            new_project_answer_ids = set()
        if not is_gap_audit:
            review_count_before_fallback = len(grounded.sentence_reviews)
            warnings.extend(
                add_substantive_answer_fallback(
                    grounded, fields,
                    [answer for answer in without_mentioned_sentences(current_answers, mentioned_answers, fields)
                     if answer.question_id not in new_project_answer_ids],
                )
            )
            if len(grounded.sentence_reviews) > review_count_before_fallback:
                # The deterministic fallback must pass the same provenance,
                # uniqueness and overlap checks as a model-generated edit.
                warnings.extend(ground_sentences(fields, evidence_answers, grounded, job_text or ""))
                warnings.extend(require_answer_reflection(grounded, turn_answers))
        if mentioned_answers:
            warnings.extend(withhold_moved_sentences(
                grounded, {answer.field_path for answer in current_answers}, mentioned_answers, fields,
            ))
        if is_focused_followup and not is_gap_audit and not skip_model:
            # 수정안을 원문·확인된 답과 뜻으로 대조하고, 빠진 사실·근거 없는 사실이 있으면 그 곳만 다시 쓰게 한다.
            # 다시 쓴 수정안도 같은 서버 검사를 통과해야 바꾼다.
            def reground(items):
                subset = ResumeReviewGeneration(summary='', section_reviews=[], sentence_reviews=items)
                ground_sentences(fields, evidence_answers, subset, job_text or "")
                require_answer_reflection(subset, turn_answers)

            warnings.extend(check_and_repair_revisions(
                grounded, fields, evidence_answers, getattr(service, '_fact_checker', None),
                getattr(service, '_fact_repairer', None), telemetry, reground,
            ))
        if not is_gap_audit:
            # 같은 응답의 경험 칸 수정안에 들어가는 숫자를 자기소개서에도 옮겨 적었으면 안내한다.
            add_pending_repeated_fact_notices(grounded, fields)
        if is_focused_followup and not is_gap_audit and not skip_model:
            # 답을 원문 뒤에 따로 붙인 수정안에 안내를 붙인다(막지 않는다).
            add_flow_notices(grounded, turn_answers)
        grounded.sentence_reviews.extend(new_project_reviews)
        if not is_gap_audit:
            apply_selected_job_identity_revisions(
                grounded,
                fields,
                job_source,
                insert_missing_identity=(
                    request.review_mode == 'job'
                    and request.tailored_resume_id is not None
                    and not is_focused_followup
                ),
            )
        # STAR 판정. 첫 첨삭은 모델이 모든 경험 칸을 판정한다. 후속 첨삭은 이전 판정을 잇고, 이번 답변이 수정안에
        # 실제로 반영됐으면 그 질문이 묻던 요소만 "있음"으로 바꾼다(모델을 다시 부르지 않는다).
        previous_stars = list((previous or {}).get('star_checks') or [])
        if is_gap_audit or skip_model:
            star_rows = [check for check in previous_stars if check.get('field_path') in fields]
        elif is_focused_followup:
            star_rows = mark_answered_star_elements(
                [check for check in previous_stars if check.get('field_path') in fields],
                current_answers, previous_questions, grounded.sentence_reviews,
            )
        else:
            judged = star_targets(prompt_fields)
            star_rows, star_warnings = ground_star_judgements(
                grounded.star_judgements, fields, answers, previous_stars, judged,
            )
            warnings.extend(star_warnings)
            star_rows = [row.model_dump() for row in star_rows]
        grounded.star_judgements = []
        if request.review_mode == 'job':
            prefer_project_evidence_over_surface_edit(grounded, fields, answers, star_rows)
        changes = normalize_diagnostics(grounded, fields, bool(job_text), previous)
        # normalize_diagnostics가 이전 방식대로 star_checks를 비우므로 확정한 판정을 그 뒤에 싣는다.
        grounded.star_checks = list(star_by_path(star_rows).values())
        requirement_rows = previous_rows
        if requirements and not is_gap_audit:
            matches = grounded.requirement_matches
            if is_focused_followup:
                matches = [m for m in matches if m.requirement_id in answered_requirement_ids]
            rows, requirement_warnings = ground_requirement_matches(
                requirements, matches, fields, answers, previous_rows,
            )
            warnings.extend(requirement_warnings)
            requirement_rows = [row.model_dump() for row in rows]
            for answer in current_answers:
                requirement_id = previous_questions.get(answer.question_id, {}).get('requirement_id')
                if requirement_id and is_none_answer(answer.answer):
                    requirement_rows = mark_requirement_absent(requirement_rows, requirement_id)
        is_first_job_review = not is_focused_followup and not is_gap_audit and request.review_mode == 'job'
        if not is_focused_followup and not is_gap_audit:
            add_thin_self_introduction_questions(
                grounded, fields, star_rows, job_review=request.review_mode == 'job',
            )
            if request.review_mode == 'job' and not requirement_rows:
                add_missing_job_technology_question(grounded, fields, job_text)
        else:
            # 누락 점검도 남은 질문을 이어받아야 한다. 첨삭마다 question_id를 새로 매기므로, 이어받지
            # 않으면 화면에 떠 있는 질문의 번호를 서버가 모르게 된다. 그러면 앱이 그 질문을 죽은 것으로
            # 보고 답을 보내지 않고 넘겨, 사용자가 친 답이 입력칸에 남은 채 다음 질문만 쌓였다
            # (2026-09-16 앱: 누락 점검 뒤 답변이 서버까지 가지 않았다).
            carry_forward_unanswered_questions(grounded, previous, answers)
        # 비슷한 질문 거르기보다 먼저 거른다. 뒤에서만 거르면 "직접 한 방법은?"(이미 적힘)이 남고 비슷한
        # "확인한 결과는?"(빠짐)이 먼저 버려져, 필요한 질문까지 사라진다. 수정안에 붙은 질문은 정리 뒤에 한 번 더 본다.
        filter_questions_by_resume_facts(grounded, fields, star_rows)
        normalize_questions(grounded, fields, answers, request.request_id)
        filter_verified_project_time_questions(grounded, time_context)
        filter_questions_by_resume_facts(grounded, fields, star_rows)
        if is_first_job_review and requirement_rows:
            # 걸러진 뒤에 남은 질문을 보고 빠진 요건 질문을 채운다. 모델이 요건 질문을 만들었는데 그 질문이
            # 위에서 걸러지면(이력서에 없는 칸, "없음" 같은 빈 질문) 요건은 "이미 물었다"로 남아 아무도 묻지
            # 않았다(2026-09-15 최종 확인: React 필수 요건에 질문이 없었다).
            add_requirement_questions(grounded, fields, requirement_rows)
            normalize_questions(grounded, fields, answers, request.request_id)
        assign_review_stages(grounded, requirement_rows)
        if fragment_targets:
            telemetry.update(noun_fragments=len(fragment_targets),
                             noun_fragments_unjoined=count_unjoined_fragments(fragment_targets, grounded.sentence_reviews))
        telemetry.update(status='complete', elapsed_ms=round((time.monotonic() - started) * 1000))
        response = FirestoreResumeReviewResponse(
            **grounded.model_dump(), review_id=request.request_id, cohort_id=request.cohort_id,
            resume_id=request.resume_id, grounding_warnings=warnings, input_fields=fields,
            input_hash=snapshot_hash, item_refs=refs, excluded_fields=excluded,
            confirmed_answers=answers, changes=changes, telemetry=telemetry, job_source=job_source,
            requirement_map=requirement_rows,
            answer_scope_paths=sorted({answer.field_path for answer in mentioned_answers}),
            tailored_resume_id=request.tailored_resume_id)
        # Persist the response on the claimed document; repeat requests recover it.
        if request.tailored_resume_id:
            db.complete_review(
                request.cohort_id,
                request.resume_id,
                uid,
                request.request_id,
                response.model_dump(),
                request.tailored_resume_id,
            )
        else:
            db.complete_review(
                request.cohort_id, request.resume_id, uid, request.request_id, response.model_dump()
            )
        return response
    except Exception as exc:
        telemetry.update(status='failed', elapsed_ms=round((time.monotonic() - started) * 1000), error_type=type(exc).__name__)
        # Do not release the claim: uncertain model/save outcomes must not silently rebill.
        try:
            if request.tailored_resume_id:
                db.fail_review(
                    request.cohort_id,
                    request.resume_id,
                    uid,
                    request.request_id,
                    telemetry,
                    request.tailored_resume_id,
                )
            else:
                db.fail_review(
                    request.cohort_id, request.resume_id, uid, request.request_id, telemetry
                )
        except Exception:
            pass
        raise
