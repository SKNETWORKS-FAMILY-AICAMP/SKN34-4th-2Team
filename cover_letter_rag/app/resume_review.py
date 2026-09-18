from __future__ import annotations

import re
from difflib import SequenceMatcher
from collections.abc import Callable
from typing import Any

from langchain_openai import ChatOpenAI

from app.config import Settings
from app.firebase_gateway import FirebaseGateway
from app.models import (
    FirestoreResumeReviewRequest,
    FirestoreResumeReviewResponse,
    ResumeReviewGeneration,
    ResumeReviewFollowupOutput,
    ResumeReviewModelOutput,
    SentenceReview,
)
from app.prompts import RESUME_REVIEW_PROMPT
from app.technology import comparison_terms, grounding_terms
from app.review_rules import (
    EXPERIENCE_DESCRIPTION, EXPERIENCE_SECTION_PATTERN, ITEM_NAME_KEYS, NARRATIVE_FIELD, NEGATION, NOT_NEGATION_WORDS,
    ABSENCE_STATEMENT, ROLE_EXPANSION_WORDS, SECTION_NAMES, WORK_NEGATION, split_uncertain_answer,
)

# 숫자와 단위("30%", "500건", "1.2초"). 앞에 영문·한글이 붙은 숫자("v2", "3차원")는 사실 숫자로 보지 않는다.
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z가-힣])\d+(?:[.,]\d+)*(?:%|명|건|개|개월|년|일|시간|분|초|ms)?")

# 같은 양을 가리키는 단위 표기. "1.2s"와 "1.2초", "40min"과 "40분"은 같은 사실이다.
_UNIT_ALIASES = {
    's': '초', 'sec': '초', '초': '초', 'ms': 'ms', 'min': '분', '분': '분',
    'h': '시간', '시간': '시간', '%': '%', '%p': '%p', '퍼센트': '%',
}
_NUMBER_FACT = re.compile(
    r'(?<![A-Za-z가-힣\d.])(\d+(?:,\d{3})*(?:\.\d+)?)\s*'
    r'(%p|%|퍼센트|ms|sec|min|s|h|초|분|시간|명|건|개월|개|년|일|배|만|천|억)?(?![A-Za-z])'
)


def _number_facts(text: str) -> set[tuple[str, str]]:
    """숫자를 (값, 단위)로 모은다. 1,000과 1000, 1.2s와 1.2초를 같게 본다."""
    facts = set()
    for value, unit in _NUMBER_FACT.findall(text or ''):
        try:
            number = float(value.replace(',', ''))
        except ValueError:
            continue
        facts.add((f'{number:g}', _UNIT_ALIASES.get(unit, unit)))
    return facts


def _unsupported_numbers(revision: str, evidence: str) -> set[tuple[str, str]]:
    """근거에 없는 숫자만 남긴다.

    단위가 같으면 같은 사실이다. 한쪽에 단위가 없으면 값만 같아도 받아 준다("1.2→0.5"를
    "1.2초에서 0.5초로"라고 쓰는 경우). 단위가 서로 다르면(1.2초 → 1.2분) 다른 사실이다.
    """
    known = _number_facts(evidence)
    bare_values = {value for value, unit in known if not unit}
    values_with_unit = {value for value, _ in known}
    unsupported = set()
    for value, unit in _number_facts(revision):
        if (value, unit) in known:
            continue
        if unit and value in bare_values:
            continue
        if not unit and value in values_with_unit:
            continue
        unsupported.add((value, unit))
    return unsupported


SECTION_LABELS = {
    "coreCompetencies": "핵심 역량",
    "experience": "경력",
    "education": "학력",
    "techStack": "기술 스택",
    "certifications": "자격증",
    "awards": "수상",
    "trainingExperience": "교육 경험",
    "otherActivities": "기타 활동",
    "projects": "프로젝트",
    "selfIntroduction": "자기소개서",
}
SECTION_KEY_ALIASES = {label: key for key, label in SECTION_LABELS.items()}
SECTION_KEY_ALIASES.update(
    {
        "핵심역량": "coreCompetencies",
        "기술스택": "techStack",
        "교육": "trainingExperience",
        "활동": "otherActivities",
        "기타활동": "otherActivities",
        "자기소개": "selfIntroduction",
    }
)
FIELD_LABELS = {
    "text": "내용",
    "company": "회사",
    "role": "역할",
    "startDate": "시작일",
    "endDate": "종료일",
    "isCurrent": "재직 중",
    "description": "설명",
    "school": "학교",
    "major": "전공",
    "status": "상태",
    "name": "이름",
    "level": "수준",
    "issuer": "발급기관",
    "acquiredDate": "취득일",
    "organization": "기관",
    "date": "날짜",
    "course": "과정",
    "techStack": "기술 스택",
    "subtitle": "소제목",
    "body": "본문",
}
SELF_INTRO_LABELS = {
    "intro": "자기소개",
    "motivation": "지원동기",
    "challenge": "어려움 극복 경험",
    "growth": "성장과정",
    "strengthsWeaknesses": "성격의 장단점",
    "aspiration": "입사 후 포부",
}
SKIPPED_FIELDS = {"id", "url", "githubUrl", "blogUrl"}


class ResumeReviewService:
    def __init__(
        self,
        settings: Settings,
        firebase: FirebaseGateway,
        generator: Callable[[dict[str, str]], ResumeReviewGeneration] | None = None,
        requirement_extractor: Callable | None = None,
        fact_checker: Callable | None = None,
        fact_repairer: Callable | None = None,
    ) -> None:
        self._settings = settings
        self._firebase = firebase
        self._generator = generator or self._build_generator(settings)
        # 공고 요건 정리 모델. 가짜 생성기로 도는 시험에서는 요건 정리도 부르지 않는다.
        if requirement_extractor is None and generator is None:
            from app.job_requirements import build_requirement_extractor
            requirement_extractor = build_requirement_extractor(settings)
        self._requirement_extractor = requirement_extractor
        # 후속 첨삭 수정안이 원문 사실을 빼거나 약하게 바꿨는지 보는 검사 모델. 가짜 생성기 시험에서는 부르지 않는다.
        if fact_checker is None and generator is None:
            from app.fact_check import build_fact_checker
            fact_checker = build_fact_checker(settings)
        self._fact_checker = fact_checker
        # 검사에 걸린 수정안의 그 곳만 고쳐 다시 쓰는 모델.
        if fact_repairer is None and generator is None:
            from app.fact_check import build_fact_repairer
            fact_repairer = build_fact_repairer(settings)
        self._fact_repairer = fact_repairer

    @staticmethod
    def _build_generator(settings: Settings):
        model = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            use_responses_api=True,
            reasoning_effort=settings.openai_reasoning_effort,
            max_retries=0,
        )
        chain = RESUME_REVIEW_PROMPT | model.with_structured_output(
            ResumeReviewModelOutput,
            method="json_schema",
            include_raw=True,
        )
        # 후속 첨삭만 새 프로젝트 제안 칸이 있는 스키마를 쓴다(첫 첨삭 출력이 늘지 않게).
        followup_chain = RESUME_REVIEW_PROMPT | model.with_structured_output(
            ResumeReviewFollowupOutput,
            method="json_schema",
            include_raw=True,
        )

        def generate(inputs):
            inputs = dict(inputs)
            allow_new_projects = inputs.pop("allow_new_projects", False)
            result = (followup_chain if allow_new_projects else chain).invoke(inputs)
            parsed = result.get("parsed")
            if parsed is not None:
                result = {**result, "parsed": ResumeReviewGeneration(section_reviews=[], **parsed.model_dump())}
            return result

        return generate

    def review(self, id_token: str, request: FirestoreResumeReviewRequest) -> FirestoreResumeReviewResponse:
        from app.review_workflow import run_review
        return run_review(self, id_token, request)


def render_resume_content(content: Any) -> str:
    """Render only review-relevant fields; basicInfo/URLs/internal IDs are excluded."""
    if not isinstance(content, dict):
        return ""
    blocks: list[str] = []
    for key, label in SECTION_LABELS.items():
        value = content.get(key)
        lines = _render_value(value, SELF_INTRO_LABELS if key == "selfIntroduction" else {})
        if lines:
            blocks.append(f"## {label}\n" + "\n".join(lines))
    return "\n\n".join(blocks)


def _render_value(value: Any, nested_labels: dict[str, str] | None = None) -> list[str]:
    nested_labels = nested_labels or {}
    if isinstance(value, list):
        lines: list[str] = []
        for index, item in enumerate(value, start=1):
            item_lines = _render_value(item)
            if item_lines:
                lines.append(f"[{index}]")
                lines.extend(item_lines)
        return lines
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if key in SKIPPED_FIELDS or item in (None, "", [], {}, False):
                continue
            label = nested_labels.get(key, FIELD_LABELS.get(key, key))
            if isinstance(item, (dict, list)):
                child_lines = _render_value(item)
                if child_lines:
                    lines.append(f"### {label}")
                    lines.extend(child_lines)
            else:
                lines.append(f"{label}: {str(item).strip()}")
        return lines
    text = str(value).strip() if value is not None else ""
    return [text] if text else []


def enforce_resume_review_grounding(
    resume_text: str,
    generation: ResumeReviewGeneration,
) -> tuple[ResumeReviewGeneration, list[str]]:
    warnings: list[str] = []
    all_questions = list(generation.confirmation_questions)
    allowed_numbers = set(NUMBER_PATTERN.findall(resume_text))
    allowed_sections = set(SECTION_LABELS)

    normalized_reviews = []
    for review in generation.section_reviews:
        review.section_key = SECTION_KEY_ALIASES.get(review.section_key.strip(), review.section_key.strip())
        if review.section_key not in allowed_sections:
            warnings.append(f"알 수 없는 섹션 첨삭을 제거했습니다: {review.section_key}")
            continue

        valid_quotes = [quote.strip() for quote in review.resume_quotes if quote.strip() and quote.strip() in resume_text]
        if len(valid_quotes) != len(review.resume_quotes):
            warnings.append(f"원문에서 확인되지 않은 인용을 제거했습니다: {review.section_key}")
        review.resume_quotes = list(dict.fromkeys(valid_quotes))

        revision = (review.suggested_revision or "").strip()
        invented_numbers = set(NUMBER_PATTERN.findall(revision)) - allowed_numbers
        if revision and (not valid_quotes or invented_numbers):
            reason = "직접 근거가 없어서" if not valid_quotes else "원문에 없는 수치가 있어서"
            warnings.append(f"{review.section_key} 첨삭안을 {reason} 제거했습니다.")
            review.suggested_revision = None
            question = "이 문장을 보완할 실제 행동·방법·결과와 확인 가능한 수치가 있나요?"
            review.confirmation_questions.append(question)
        review.confirmation_questions = _deduplicate(review.confirmation_questions)[:3]
        all_questions.extend(review.confirmation_questions)
        normalized_reviews.append(review)

    generation.section_reviews = normalized_reviews
    generation.confirmation_questions = _deduplicate(all_questions)[:30]
    return generation, _deduplicate(warnings)


def extract_review_fields(content: Any) -> tuple[dict[str, str], list[str]]:
    """Preserve field values and array positions without summarizing source content."""
    fields, excluded = {}, []

    def walk(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else key
                if key in SKIPPED_FIELDS or (not path and key not in SECTION_LABELS):
                    excluded.append(child_path)
                elif key in FIELD_LABELS or key in SELF_INTRO_LABELS or key in SECTION_LABELS:
                    walk(child, child_path)
                else:
                    excluded.append(child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
        elif isinstance(value, str) and value.strip():
            fields[path] = value
        elif isinstance(value, bool):
            fields[path] = str(value).lower()

    if isinstance(content, dict):
        walk(content, "")
    return fields, excluded


_SCOPE_CLARIFIED = re.compile(r'직접|맡았|맡아|담당|제가|본인이|혼자|단독')


def _without_non_negation_words(text: str) -> str:
    return NOT_NEGATION_WORDS.sub(' ', text or '')


def _negation_notice(original: str, revision: str, answer_text: str = '') -> str | None:
    """원문의 부정 표현이 수정안에서 빠졌지만 한 일을 뒤집은 게 아니면 사용자에게 보일 안내를 돌려준다.

    "사용자가 불편을 겪지 않는 API를 만들고 싶습니다"는 바람이다. 답변 사실을 넣어 다시 쓰다 이 표현이 빠지면
    예전에는 수정안을 통째로 버렸다(2026-09-15 새 케이스 Node 자기소개, 세 번 모두). 한 일을 부정하는 표현
    ("구현하지 못했습니다"), 수정안에 새로 생긴 부정, 같은 말을 긍정으로 뒤집은 것("나지 않도록" → "나도록")은
    None을 돌려 계속 막는다.
    """
    original, revision, answer_text = (
        _without_non_negation_words(original), _without_non_negation_words(revision), _without_non_negation_words(answer_text))
    if not re.search(NEGATION, original) or re.search(NEGATION, revision):
        return None
    if WORK_NEGATION.search(original) and not WORK_NEGATION.search(answer_text):
        return None
    for stem, ending in re.findall(r'(\S+?)지\s*않(\S*)', original):
        if ending and f'{stem}{ending}' in revision:
            return None  # "나지 않도록" → "나도록"
    phrase = re.search(r'(?:\S+\s+)?\S*(?:않|없|아니)\S*', original)
    shown = phrase.group(0).strip(' .,') if phrase else '부정'
    return f"원문의 '{shown}' 표현이 수정안에서 빠졌어요. 뜻이 달라지지 않았는지 확인해 주세요."


def _meaning_risks(original, revision, answer_text=''):
    """Conservative lexical checks, not a proof of semantic equivalence.

    답변이 근거인 수정은 원문만이 아니라 답변과도 견준다. "팀원들과 함께 개선했습니다"에
    "PDF 파싱·검색은 제가 맡았고 화면은 팀원이 만들었습니다"라고 답하면, 본인 범위만 적은
    수정안은 협업 표현이 빠졌어도 사실을 바꾼 게 아니다. 예전에는 원문과만 견줘 이런 수정안을
    버렸다(2026-09-15 목업 첨삭에서 답 반영 실패 6건 중 4건).
    """
    patterns = {
        'negation_changed': NEGATION,
        'work_status_changed': r'예정|계획|진행\s*중|개발\s*중|구현\s*중|검토\s*중|학습\s*중',
        'ownership_changed': r'팀원|공동|협업|보조|지원받|도움|AI 코딩',
    }
    issues = []
    for code, pattern in patterns.items():
        texts = (original, revision, answer_text)
        if code == 'negation_changed':
            texts = tuple(_without_non_negation_words(text) for text in texts)
        in_original = bool(re.search(pattern, texts[0]))
        in_revision = bool(re.search(pattern, texts[1]))
        if in_original == in_revision:
            continue
        in_answer = bool(re.search(pattern, texts[2]))
        if in_revision and in_answer:
            continue  # 답변에 있는 표현을 옮겨 적었다.
        if code == 'negation_changed' and _negation_notice(original, revision, answer_text):
            continue  # 바람·목적을 말하는 부정 표현이 빠졌을 뿐이다. 막지 않고 안내만 붙인다.
        if code == 'ownership_changed' and in_original and _SCOPE_CLARIFIED.search(answer_text):
            continue  # 답변이 본인 범위를 밝혔다.
        issues.append(code)
    # Keep signed quantities distinct; ordinary NUMBER_PATTERN ignores the sign.
    signed = r'(?<!\w)[+−-]\d+(?:[.,]\d+)*(?:%|명|건|개|개월|년|일|시간|분|초|ms)?'
    if set(re.findall(signed, original)) != set(re.findall(signed, revision)):
        issues.append('quantity_sign_changed')
    return issues


def _fact_anchors(text: str) -> list[str]:
    """Return only deterministic anchors that must survive a sentence rewrite.

    Korean free text is intentionally not tokenized here: an imprecise tokenizer could
    label ordinary wording as a protected fact. Numbers and technology/English tokens
    are stable enough to verify locally.
    """
    numbers = set(NUMBER_PATTERN.findall(text))
    terms = {term.removeprefix('tech:') for term in comparison_terms(text)}
    return sorted(numbers | terms, key=str.casefold)


def _change_rate(original: str, revision: str) -> float:
    source = re.sub(r'\s+', '', original)
    target = re.sub(r'\s+', '', revision)
    if not source and not target:
        return 0.0
    return round(1 - SequenceMatcher(a=source, b=target, autojunk=False).ratio(), 3)


_SURFACE_EDITS = {'spelling', 'tone', 'clarity'}
# 문장이 아니라 짧은 값을 담는 칸. 여기에 답변 문장을 써 넣으면 안 된다.
_NOMINAL_FIELD = re.compile(
    rf'techStack\[\d+\]\.(?:name|level)|(?:{EXPERIENCE_SECTION_PATTERN}|education|certifications)'
    r'\[\d+\]\.(?:name|company|role|course|organization|school|major|issuer|techStack|status)|selfIntroduction\.[^.]+\.subtitle'
)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r'(?<=[.!?다요])\s+|\n', str(text or '').strip()) if len(s.strip()) >= 6]

# "여러 방법을 시도해 해결했습니다"처럼 무엇을 했는지 없는 해결 문장. 지시문 49번이 action 근거로 치지 않는 표현이다.
_VAGUE_RESOLUTION = re.compile(r'(?:여러|다양한|이것저것)\s*(?:가지\s*)?(?:방법|방식|시도|것)')


def _drop_superseded_vague_sentence(original_quote: str, revision: str) -> str:
    """답변으로 방법을 채우면서 원문의 막연한 해결 문장을 지우지 않은 수정안에서 그 문장만 덜어낸다.

    모델이 "'여러 방법을 시도해 해결했습니다'를 구체화했습니다"라고 적어 놓고 그 문장을 그대로 두어,
    "라우터를 제가 직접 만들었습니다. 팀원들과 여러 방법을 시도해 해결했습니다."처럼 앞뒤가 어긋난
    수정안이 나왔다(2026-09-16 앱). 원문에 있던 그 문장만 빼고 나머지는 모델이 쓴 그대로 둔다.
    """
    sentences = _sentences(revision)
    if len(sentences) <= 1:
        return revision
    # 답이 반영돼 새 문장이 들어온 수정안에만 손댄다. 원문을 그대로 돌려준 수정안에서 문장을 빼면
    # 고치지도 않은 사실이 사라진다.
    if not [s for s in sentences if s.strip() not in original_quote]:
        return revision
    kept = [s for s in sentences
            if not (_VAGUE_RESOLUTION.search(s) and s.strip() in original_quote)]
    if len(kept) == len(sentences) or not kept:
        return revision
    return ' '.join(s.strip() for s in kept)


# 합니다체가 아닌 문장 끝: "API 개발.", "만들었음.", "개발 중이에요."
_NON_FORMAL_ENDING = re.compile(r'[가-힣A-Za-z0-9)](?<!다)\.(?:\s|$)|[가-힣](?<!다)$')
_FORMAL_ENDING = re.compile(r'다\.(?:\s|$)|다$')
# 빼면 읽기 쉬워지는 군더더기. 항목마다 따로 센다(한 정규식으로 세면 "진행 하였습니다"의 두 군데가 하나로 겹친다).
_FILLER_PATTERNS = [re.compile(p) for p in (
    r'진행\s*(?:하|했|해|을|되|됐)', r'통해', r'에\s*있어서?', r'에서의', r'하였', r'되었', r'할\s*수\s*있었',
)]
# 이력서에 자주 나오는 맞춤법 오류. 한 글자만 고쳐도 쓸모 있는 수정이다.
_MISSPELLINGS = re.compile(
    r'됬|되서|되요|몇일|금새|할께|할꺼|역활|틈틈히|꼼꼼이|일일히|번번히|곰곰히|깨끗히|희안|설레임|바램|않하|않되|웬지|오랫만'
)


def _is_minor_rewording(original: str, revision: str) -> bool:
    """표현 수정이 뜻이 같은 단어 몇 개만 바꾼 것인가.

    "재 보는"→"다시 보는", "붙였습니다"→"추가했습니다", "서비스로"→"서비스에"처럼 한두 단어만 바꾼 수정은
    읽기 쉬워지지 않고 뜻만 흔들린다. 숫자·기술어 검사로는 잡히지 않는다. 2026-09-15 자세한 이력서 목업에서
    문장 다듬기 22개 중 17개가 이런 수정이었다(변경 폭 중앙값 3%). 띄어쓰기, 합니다체로 맞추기, 명사형으로
    끊긴 문장 잇기, 문장 나누기, 군더더기 빼기, 흔한 맞춤법 오류 고치기는 작아도 쓸모가 있어 남긴다.
    """
    before_words, after_words = original.split(), revision.split()
    for op, i1, i2, j1, j2 in SequenceMatcher(a=before_words, b=after_words, autojunk=False).get_opcodes():
        if op != 'equal' and ''.join(before_words[i1:i2]) and ''.join(before_words[i1:i2]) == ''.join(after_words[j1:j2]):
            return False  # 띄어쓰기 교정
    if len(_NON_FORMAL_ENDING.findall(original)) > len(_NON_FORMAL_ENDING.findall(revision)):
        return False
    if len(_FORMAL_ENDING.findall(revision)) > len(_FORMAL_ENDING.findall(original)):
        return False
    if any(len(p.findall(original)) > len(p.findall(revision)) for p in _FILLER_PATTERNS):
        return False
    if len(_MISSPELLINGS.findall(original)) > len(_MISSPELLINGS.findall(revision)):
        return False
    source, target = re.sub(r'\s+', '', original), re.sub(r'\s+', '', revision)
    opcodes = SequenceMatcher(a=source, b=target, autojunk=False).get_opcodes()
    changed = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in opcodes if op != 'equal')
    return changed <= 6 or _change_rate(original, revision) < 0.05


_DUPLICATE_TOKEN_SUFFIX = re.compile(
    r'(?:으로|에서|에게|까지|부터|처럼|보다|하고|하며|해서|하여|되는|되던|되도록|'
    r'했습니다|하였다|합니다|된다|되며|되어|된|하는|한|할|했던|했다|을|를|은|는|이|가|과|와|의|에|로)$'
)
_DUPLICATE_TOKEN_STOPWORDS = {
    '사용자', '내용', '기능', '과정', '결과', '문장', '이력서', '프로젝트',
    '개발', '구현', '확인', '수정', '적용', '통해', '위해', '대한', '관련',
    '있습니다', '했습니다', '합니다', '것입니다', '수있습니다',
}


def _duplicate_content_tokens(text: str) -> set[str]:
    tokens = set()
    for token in re.findall(r'[가-힣A-Za-z][가-힣A-Za-z0-9·-]{1,}', text.lower()):
        normalized = _DUPLICATE_TOKEN_SUFFIX.sub('', token).strip('·-')
        if len(normalized) >= 2 and normalized not in _DUPLICATE_TOKEN_STOPWORDS:
            tokens.add(normalized)
    return tokens


def _answer_reflection_anchors(text: str) -> tuple[set[str], set[str]]:
    """Return stable facts and tolerant Korean content tokens from an answer."""
    stable = grounding_terms(text) | {f'{value}{unit}' for value, unit in _number_facts(text)}
    return stable, _duplicate_content_tokens(text)


def _answer_is_reflected(original: str, revision: str, answer: str) -> bool:
    """Allow an answer-backed paraphrase without requiring a verbatim quote."""
    answer_stable, answer_content = _answer_reflection_anchors(answer)
    original_stable, original_content = _answer_reflection_anchors(original)
    revision_stable, revision_content = _answer_reflection_anchors(revision)
    new_stable = answer_stable - original_stable
    new_content = answer_content - original_content
    if new_stable & revision_stable:
        return True
    return len(new_content & revision_content) >= 2


def _paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r'\n\s*\n', text) if len(part.strip()) >= 40]




def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r'(?<=[.!?다요])\s+|\n', str(text or '')) if len(s.strip()) >= 12]


def _cross_field_overlap(field_path: str, original_quote: str, revision: str, fields: dict) -> tuple[bool, str | None]:
    """수정안이 다른 칸의 문장을 옮겨 적었는지 본다.

    같은 사례를 여러 칸에서 다른 관점으로 말하는 것은 이력서에서 정상이다. 그래서 막는 건 거의 그대로 베낀 문장
    (유사도 0.9 이상)뿐이고, 비슷한 문장(0.72 이상)은 안내만 붙여 사용자가 고르게 한다(2026-09-15 새 케이스에서
    틀 질문 답의 프로젝트 성과가 자기소개·어려움 극복 칸에 그대로 들어갔다). 원문에 이미 있던 문장은 보지 않는다.
    """
    if not NARRATIVE_FIELD.fullmatch(field_path):
        return False, None
    squash = lambda t: re.sub(r'[\s\W_]+', '', t)  # noqa: E731
    own = [squash(s) for s in _split_sentences(original_quote)]
    # 경험 칸은 사례의 원래 자리다. 자기소개서·핵심역량이 같은 사례를 이미 쓰고 있어도 경험 칸 수정안에 안내를 붙이지 않는다
    # (2026-09-15 새 케이스 v16m: 프로젝트 설명 다듬기에 "자기소개서 칸과 비슷한 문장이 있어요"가 붙었다).
    experience_field = bool(EXPERIENCE_DESCRIPTION.fullmatch(field_path))
    others = [(path, squash(s)) for path, text in fields.items()
              if path != field_path and NARRATIVE_FIELD.fullmatch(path)
              and (not experience_field or EXPERIENCE_DESCRIPTION.fullmatch(path))
              for s in _split_sentences(text)]
    verbatim, similar = False, set()
    for sentence in _split_sentences(revision):
        key = squash(sentence)
        if any(SequenceMatcher(None, key, o).ratio() >= 0.8 for o in own):
            continue
        for path, other in others:
            ratio = SequenceMatcher(None, key, other).ratio()
            if ratio >= 0.9:
                verbatim = True
            elif ratio >= 0.72:
                similar.add(SECTION_NAMES.get(re.match(r'[A-Za-z]+', path).group(0), path))
    if verbatim:
        return True, None
    if similar:
        return False, f"{'·'.join(sorted(similar))} 칸과 비슷한 문장이 있어요. 같은 이야기를 두 번 쓰는 게 아닌지 확인해 주세요."
    return False, None


_BEFORE_AFTER = re.compile(r'(\d+(?:[.,]\d+)?)\s*\D{0,3}?\s*(?:에서|→|->|~)\s*(\d+(?:[.,]\d+)?)')


_APPENDED_PARAGRAPH = re.compile(r'^\s*(?:또한|그리고|아울러|더불어|이외에도|그\s*외에도|추가로|뿐만\s*아니라)[\s,]')


def add_flow_notices(generation, answers) -> None:
    """답을 원문 뒤에 "또한 …" 문단으로만 덧붙인 후속 첨삭 수정안에 안내를 붙인다. 막지 않는다.

    자기소개서 수정안이 답을 원문 끝에 "또한 …" 별도 문단으로 붙여 앞 문장과 이어지지 않았다(2026-09-15 한 번도 안 본
    케이스). 원문이 그대로 앞에 남고 뒤에 접속어로 시작하는 새 덩어리만 붙은 경우만 본다.
    """
    if not answers:
        return
    squash = lambda text: re.sub(r'\s+', '', str(text or ''))  # noqa: E731
    for review in generation.sentence_reviews:
        revision, original = review.suggested_revision or '', review.original_quote or ''
        if not revision or not original or review.new_item is not None:
            continue
        if not squash(revision).startswith(squash(original)):
            continue
        tail = revision[len(original):] if revision.startswith(original) else revision.split(original.strip()[-8:], 1)[-1]
        if _APPENDED_PARAGRAPH.match(tail):
            review.flow_notice = '답변 내용이 원문 뒤에 따로 붙었어요. 앞 문장과 한 흐름으로 이어지는지 확인해 주세요.'


def add_pending_repeated_fact_notices(generation, fields) -> None:
    """같은 응답에서 경험 칸에 새로 들어가는 수치가 자기소개서 수정안에도 둘 이상 들어가면 안내를 붙인다.

    틀 질문(자기소개·어려움 극복)에 답하며 프로젝트 성과를 처음 말하면, 그 숫자가 프로젝트 칸 수정안과 자기소개서
    수정안에 함께 들어갔다. 원문 다른 칸에는 없던 숫자라 `_repeated_facts_notice`가 안내를 붙이지 못했다(2026-09-15
    한 번도 안 본 케이스). 같은 응답의 경험 칸 수정안을 그 칸 내용에 더해 한 번 더 본다. 막지 않는다.
    """
    pending = dict(fields)
    for review in generation.sentence_reviews:
        if review.suggested_revision and review.new_item is None and EXPERIENCE_DESCRIPTION.fullmatch(review.field_path):
            pending[review.field_path] = f"{pending.get(review.field_path, '')}\n{review.suggested_revision}"
    if pending == fields:
        return
    for review in generation.sentence_reviews:
        if review.suggested_revision and not review.overlap_notice:
            review.overlap_notice = _repeated_facts_notice(
                review.field_path, review.original_quote, review.suggested_revision, pending, fields)


def _repeated_facts_notice(field_path: str, original_quote: str, revision: str, fields: dict,
                           written_fields: dict | None = None) -> str | None:
    """자기소개서 수정안이 경험 칸의 수치 사실 여러 개를 표현만 바꿔 다시 적었으면 안내를 돌려준다.

    문장 유사도로는 잡히지 않는다. "500건을 한 번에 받던 목록을 20건씩 불러오는 무한 스크롤로 개선했습니다"는 프로젝트
    칸 문장과 표현이 달라 유사도가 0.72 아래였다(2026-09-15 새 케이스 v16j). 그 칸에 없던 수치 중 한 경험 칸에 이미
    있는 것이 둘 이상이면 알린다. "1.2초에서 0.5초로"처럼 전후 한 쌍은 하나로 센다(한 구절로 가리키는 건 괜찮다).
    막지 않는다.
    """
    if not re.fullmatch(r'selfIntroduction\.[^.]+\.body', field_path):
        return None
    own = f"{fields.get(field_path, '')}\n{original_quote}"
    new_numbers = _unsupported_numbers(revision, own)
    if len(new_numbers) < 2:
        return None
    best = None
    for path, text in fields.items():
        match = EXPERIENCE_DESCRIPTION.fullmatch(path)
        if not match:
            continue
        found = new_numbers - _unsupported_numbers(revision, text)
        values = {value for value, _ in found}
        groups = len(found)
        for left, right in _BEFORE_AFTER.findall(revision):
            if {f"{float(left.replace(',', '')):g}", f"{float(right.replace(',', '')):g}"} <= values:
                groups -= 1
        if groups >= 2 and (best is None or groups > best[0]):
            best = (groups, match, found)
    if best is None:
        return None
    _, match, found = best
    section, index = match.groups()
    name = str(fields.get(f'{section}[{index}].{ITEM_NAME_KEYS[section]}') or '').strip()
    label = f"'{name}' {SECTION_NAMES[section]}" if name else SECTION_NAMES[section]
    facts = '·'.join(f'{value}{unit}' for value, unit in sorted(found, key=lambda f: revision.find(f[0]))[:3])
    # written_fields가 있으면 fields는 같은 응답의 수정안까지 더한 내용이다. 원문에 없던 숫자면 "이미 있는"이 아니다.
    path = f'{section}[{index}].description'
    already = written_fields is None or not (found & _number_facts(fields[path])) - _number_facts(written_fields.get(path, ''))
    where = '칸에 이미 있는' if already else '칸 수정안에도 들어가는'
    return (f"{label} {where} {facts} 내용을 자기소개서에 다시 적었어요. "
            '자기소개서에서는 그 경험을 한 구절로만 가리키는 게 좋아요.')


def _adds_duplicate_paragraph(original: str, revision: str) -> bool:
    """Detect a newly appended paragraph that merely repeats an existing one.

    This intentionally targets long additions. Short wording corrections and a
    single new fact remain eligible for review.
    """
    source_paragraphs = _paragraphs(original)
    revised_paragraphs = _paragraphs(revision)
    if not source_paragraphs or len(revised_paragraphs) < 2:
        return False
    for candidate in revised_paragraphs:
        if len(candidate) < 100:
            continue
        compact_candidate = re.sub(r'\s+', '', candidate)
        candidate_tokens = _duplicate_content_tokens(candidate)
        if len(candidate_tokens) < 8:
            continue
        for source in source_paragraphs:
            # Retaining an unchanged source paragraph in a whole-field edit is
            # normal. Only inspect a genuinely new paragraph.
            if SequenceMatcher(
                a=compact_candidate,
                b=re.sub(r'\s+', '', source),
                autojunk=False,
            ).ratio() >= 0.88:
                continue
            shared = candidate_tokens & _duplicate_content_tokens(source)
            if len(shared) >= 6 and len(shared) / len(candidate_tokens) >= 0.32:
                return True
    return False


def require_answer_reflection(generation, answers):
    """Reject a follow-up edit that ignores the fact the user just confirmed.

    A confirmation question is for adding/verifying a fact, not a trigger for
    an unrelated grammar rewrite.  We deliberately use a conservative lexical
    check: if no newly supplied factual token survives in the revision, do not
    offer it as an answer-derived suggestion.
    """
    warnings = []
    if not answers:
        return warnings

    by_path = {}
    for answer in answers:
        by_path.setdefault(answer.field_path, []).append(answer)
    for item in generation.sentence_reviews:
        revision = (item.suggested_revision or '').strip()
        provided = by_path.get(item.field_path, [])
        if not revision or not provided:
            continue
        reflects_answer = any(
            _answer_is_reflected(item.original_quote, revision, answer.answer)
            for answer in provided
        )
        role_boundary_question = any(
            re.search(r'(팀원|담당\s*범위|역할\s*구분)', answer.question)
            for answer in provided
        )
        exposes_team_detail = bool(
            role_boundary_question
            and re.search(r'(팀원은|팀원이|팀원의\s*담당|다른\s*팀원)', revision)
        )
        if exposes_team_detail or not reflects_answer:
            item.suggested_revision = None
            item.status = 'unchanged'
            item.edit_type = 'none'
            item.confirmation_question = None
            issue = 'team_scope_exposed' if exposes_team_detail else 'answer_not_reflected'
            item.validation_issues = [*item.validation_issues, issue]
            warnings.append(f'답변 근거를 반영하지 않은 수정안을 제외했습니다: {item.field_path}')
    return warnings


def _merge_original_with_confirmed_answer(original: str, confirmed: str) -> str:
    """Keep only original sentences whose facts are not already in the answer."""
    confirmed = re.sub(r'[ \t]+', ' ', confirmed).strip()
    answer_stable, answer_content = _answer_reflection_anchors(confirmed)
    original_stable, original_content = _answer_reflection_anchors(original)
    overall_overlap = (
        len(original_content & answer_content) / len(original_content)
        if original_content
        else 0
    )
    # A detailed answer that covers most of the original paragraph is already
    # the integrated replacement. Keeping old sentences would merely repeat it.
    stable_overlap = original_stable & answer_stable
    # 답이 원문 내용을 되풀이해도 원문의 숫자 결과를 모두 담지 않았으면 답으로 통째 바꾸지 않는다(2026-09-15 한 번도
    # 안 본 케이스: 원문 상황 문장과 숫자 결과가 답 한 문장으로 바뀌며 사라졌다).
    if overall_overlap >= 0.3 and not _unsupported_numbers(original, confirmed) and (
        not original_stable or stable_overlap or len(answer_content) >= 12
    ):
        return confirmed
    preserved = []
    for sentence in re.split(r'(?<=[.!?])\s+', original.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        sentence_stable, sentence_content = _answer_reflection_anchors(sentence)
        stable_covered = bool(sentence_stable) and sentence_stable <= answer_stable
        shared = sentence_content & answer_content
        content_covered = bool(sentence_content) and (
            len(shared) / len(sentence_content) >= 0.45
        )
        numbers_lost = bool(_unsupported_numbers(sentence, confirmed))
        if numbers_lost or (not stable_covered and not content_covered):
            preserved.append(sentence)
    parts = [*preserved, confirmed]
    return ' '.join(dict.fromkeys(part for part in parts if part))


def _fallback_edit_scope(original: str, confirmed: str) -> tuple[str, str] | None:
    """Build a fallback edit for one uniquely identifiable paragraph.

    A field may contain several paragraphs. Rewriting that whole field makes a
    small answer look like a large edit and used to collapse its blank lines.
    Prefer the paragraph sharing the most confirmed facts; when the answer is a
    genuinely new topic, append it after the final unique paragraph. If no
    paragraph can be located unambiguously, skip the fallback rather than risk
    applying it to the wrong place.
    """
    paragraphs = [
        part.strip()
        for part in re.split(r'\r?\n[ \t]*\r?\n', original)
        if part.strip()
    ]
    if not paragraphs:
        return None

    answer_stable, answer_content = _answer_reflection_anchors(confirmed)

    def relevance(paragraph: str) -> tuple[int, int]:
        stable, content = _answer_reflection_anchors(paragraph)
        return len(stable & answer_stable), len(content & answer_content)

    ranked = sorted(
        enumerate(paragraphs),
        key=lambda item: (*relevance(item[1]), item[0]),
        reverse=True,
    )
    _, target = ranked[0]
    if original.count(target) != 1:
        return None

    if relevance(target) == (0, 0):
        # There is no defensible existing paragraph to rewrite. Add a separate
        # paragraph next to the final unique paragraph and leave all others byte
        # for byte unchanged.
        target = paragraphs[-1]
        if original.count(target) != 1:
            return None
        return target, f'{target}\n\n{confirmed}'

    return target, _merge_original_with_confirmed_answer(target, confirmed)


def _concise_company_fit_answer(path: str, question: str, confirmed: str) -> str:
    """Keep a motivation fallback focused on company duty and one evidence sentence."""
    if path != 'selfIntroduction.motivation.body' or not re.search(
        r'주요\s*업무|지원\s*회사|직무.*연결', question,
    ):
        return confirmed
    sentences = [
        sentence.strip()
        for sentence in re.split(r'(?<=[.!?])\s+', confirmed)
        if sentence.strip()
    ]
    if not sentences:
        return confirmed
    selected = [sentences[0]]
    evidence = next(
        (
            sentence for sentence in sentences[1:]
            if re.search(r'(구현|개발|설계|분석|처리|검증|운영|구축|적용)', sentence)
        ),
        None,
    )
    if evidence:
        selected.append(evidence)

    company_match = re.search(r'^(.{1,80}?)의\s*주요\s*업무', question.strip())
    if company_match and re.match(r'^주요\s*업무', selected[0]):
        selected[0] = re.sub(
            r'^주요\s*업무',
            f'{company_match.group(1)}의 주요 업무',
            selected[0],
            count=1,
        )
    return ' '.join(selected)


def _resume_endings(text: str) -> str:
    """채팅 말투 끝맺음("붙였어요", "해요", "이에요")을 이력서 말투("붙였습니다")로 바꾼다.

    답을 그대로 붙이는 대체 수정안에 "캐시를 붙였어요"가 이력서 문장으로 들어갔다(2026-09-15 한 번도 안 본 케이스,
    사람 말투 답). 받침 ㅆ으로 끝나는 말(했·었·았·있)과 해요·돼요·이에요만 바꾼다. 그 밖의 끝맺음은 그대로 둔다.
    """
    def past(match):
        stem = match.group(1)
        return f'{stem}습니다' if (ord(stem) - 0xAC00) % 28 == 20 else match.group(0)

    text = re.sub(r'([가-힣])어요(?=[.!?]|\s|$)', past, str(text or ''))
    text = re.sub(r'(?:이에요|예요)(?=[.!?]|\s|$)', '입니다', text)
    text = re.sub(r'해요(?=[.!?]|\s|$)', '합니다', text)
    return re.sub(r'돼요(?=[.!?]|\s|$)', '됩니다', text)


def _uncertain_fact_written(revision: str, uncertain: str, known: str) -> bool:
    """확신하지 못한 답 문장에만 있는 숫자·기술어나 내용 낱말이 수정안에 들어갔는가."""
    known_stable, known_content = _answer_reflection_anchors(known)
    uncertain_stable, uncertain_content = _answer_reflection_anchors(uncertain)
    revision_stable, revision_content = _answer_reflection_anchors(revision)
    if (uncertain_stable - known_stable) & revision_stable:
        return True
    shared = (uncertain_content - known_content) & revision_content
    return len(shared) >= 2 or any(len(token) >= 3 for token in shared)


def _split_answer_sentences(text: str) -> list[str]:
    """답변을 문장 부호와 줄바꿈으로 나눈다. "주요 업무"처럼 낱말 끝의 "요"에서는 나누지 않는다."""
    return [part.strip() for part in re.split(r'(?<=[.!?])\s+|\n+', str(text or '').strip()) if part.strip()]


# 답이 막연한 소감이 아니라 구체적인 일을 말했는가. 행동을 적은 말과 측정된 결과를 적은 말을 함께 본다.
# 사용자는 "줄였습니다"(내가 줄임)보다 "줄었어요"(결과가 줄어듦)로 쓰는 일이 많다. 결과형이 빠져 있던 탓에
# 숫자 근거가 다섯 개나 담긴 답이 통째로 버려졌다(2026-09-16 앱: "6초 걸리던 게 1.5초로 줄었어요.
# 맞는 문서를 가져온 질문이 25에서 36개로 늘었고요" — 동사가 하나도 안 걸려 수정안이 안 떴다).
_SUBSTANTIVE_ACTION = re.compile(
    # 행동
    r'(구현|개발|적용|측정|분석|확인|운영|설계|수정|개선|구축|처리|단축'
    r'|바꾸|바꿔|바꿨|고치|고쳐|고친|고쳤|만들|붙였|나눴|추가|도입|교체|조정|튜닝'
    # 결과
    r'|줄였|줄어|줄었|늘렸|늘어|늘었|높였|높아|낮췄|낮아|빨라|올랐|올렸)'
)


def add_substantive_answer_fallback(generation, fields, answers):
    """Add a safe proposal if the model drops a substantive confirmed answer."""
    warnings = []
    negative_answer = re.compile(
        r'(모르겠|기억(?:이\s*)?나지|없습니다|없어요|하지\s*않았|못했|해본\s*적\s*없)'
    )

    def keep(sentence):
        return not negative_answer.search(sentence) and not ABSENCE_STATEMENT.search(sentence)
    for answer_index, answer in enumerate(answers):
        path = answer.field_path
        original = fields.get(path, '').strip()
        confirmed = _concise_company_fit_answer(
            path, answer.question, answer.answer.strip(),
        )
        # 사실과 "없다"가 섞인 답은 없다고 한 문장만 뺀다. 예전에는 "없어요"가 한 번만 들어 있어도 답 전체를 버려,
        # "50건 테스트로 중복 예약 0건을 확인했습니다. 느린 점을 보완한 행동은 없어요."의 앞 문장까지 사라졌다
        # (2026-09-15 새 케이스 v16m, 모델도 수정안을 내지 않았다).
        # 확신하지 못한 문장("아마 30개쯤 했던 것 같아요")은 확인된 사실이 아니라 옮기지 않는다.
        confirmed = split_uncertain_answer(confirmed)[0]
        factual = ' '.join(
            sentence for sentence in _split_answer_sentences(confirmed)
            if keep(sentence)
        )
        if factual and factual != confirmed:
            confirmed = factual
        confirmed = _resume_endings(confirmed)
        already_present = bool(original) and (
            re.sub(r'\s+', '', confirmed) in re.sub(r'\s+', '', original)
        )
        if already_present:
            warnings.append(f'answer_already_present:{path}')
            continue
        if (
            not original
            or len(confirmed) < 80
            or not keep(confirmed)
            or any(
                item.field_path == path and item.suggested_revision
                for item in generation.sentence_reviews
            )
        ):
            continue
        stable, content = _answer_reflection_anchors(confirmed)
        has_action = bool(_SUBSTANTIVE_ACTION.search(confirmed))
        if not has_action or (not stable and len(content) < 6):
            continue
        scoped = _fallback_edit_scope(original, confirmed)
        if scoped is None:
            warnings.append(f'ambiguous_fallback_scope:{path}')
            continue
        original_quote, revision = scoped
        if re.sub(r'\s+', '', revision) == re.sub(r'\s+', '', original):
            warnings.append(f'answer_already_present:{path}')
            continue
        generation.sentence_reviews.append(
            SentenceReview(
                field_path=path,
                original_quote=original_quote,
                reason='사용자가 확인한 직접 행동과 결과를 기존 내용에 보완했습니다.',
                suggested_revision=revision,
                evidence_quotes=[original_quote, confirmed],
                status='improved',
                edit_type='content',
                evidence_sources=[path, f'answer:{answer_index}'],
                fact_anchors=_fact_anchors(original_quote),
                change_rate=_change_rate(original_quote, revision),
            )
        )
    return warnings


def ground_sentences(fields, answers, generation, job_text=''):
    warnings, valid = [], []
    spans = {}
    for item in generation.sentence_reviews:
        item.validation_issues = []
        item.fact_anchors = []
        item.change_rate = None
        item.change_rate_notice = None
        item.overlap_notice = None
        item.meaning_notice = None
        item.fact_notice = None
        item.flow_notice = None
        item.new_item = None  # 새 항목 수정안은 서버만 만든다(add_new_project_proposals).
        original = fields.get(item.field_path, "")
        if not item.original_quote.strip() or item.original_quote not in original:
            warnings.append(f"문장 원문 위치 불일치: {item.field_path}")
            continue
        # Never offer ambiguous/overlapping changes that the apply API will reject.
        starts = [m.start() for m in re.finditer('(?=' + re.escape(item.original_quote) + ')', original)]
        if len(starts) != 1:
            warnings.append(f"문장 위치가 여러 곳이라 수정안을 제외했습니다: {item.field_path}")
            continue
        start, end = starts[0], starts[0] + len(item.original_quote)
        if any(start < b and a < end for a, b in spans.get(item.field_path, [])):
            warnings.append(f"중복 또는 겹친 수정안을 제외했습니다: {item.field_path}")
            continue
        from app.review_workflow import group
        source_map = {p: v for p, v in fields.items() if group(p) == group(item.field_path)}
        # 확신하지 못한 답 문장("아마 30개쯤 했던 것 같아요")은 확인된 근거가 아니다. 그 문장에만 있는 숫자·기술어는
        # 근거 없는 숫자·용어로 걸리고, 내용 낱말이 들어가면 uncertain_fact_written으로 막는다(2026-09-15 한 번도 안 본
        # 케이스: 불확실한 답이 단정문 수정안이 됐다).
        split_answers = {
            f'answer:{i}': split_uncertain_answer(a.answer)
            for i, a in enumerate(answers)
            if group(a.field_path) == group(item.field_path)
        }
        answer_source_map = {key: confirmed for key, (confirmed, _) in split_answers.items()}
        uncertain_sentences = [sentence for _, uncertain in split_answers.values() for sentence in uncertain]
        source_map.update(answer_source_map)
        sources = list(source_map.values())
        quotes = list(dict.fromkeys(q for q in item.evidence_quotes if q.strip() and any(q in s for s in sources)))
        # The verified original is always evidence for a minimal language edit.
        if item.original_quote not in quotes:
            quotes.insert(0, item.original_quote)
        revision = item.suggested_revision or ""
        # 답변으로 방법을 채운 수정안에 원문의 막연한 해결 문장이 그대로 남으면 덜어낸다.
        if revision.strip() and answer_source_map:
            repaired = _drop_superseded_vague_sentence(item.original_quote, revision)
            if repaired != revision:
                revision = repaired
                item.suggested_revision = repaired
                item.flow_notice = '답변으로 방법이 드러나, 원문의 "여러 방법을 시도" 문장은 뺐습니다.'
        # Confirmed answers are grounding even when the model paraphrases them or
        # forgets to repeat the answer verbatim in evidence_quotes.
        evidence = "\n".join([*quotes, *answer_source_map.values()])
        new_numbers = _unsupported_numbers(revision, evidence)
        allowed_terms = grounding_terms(evidence)
        if job_text and item.field_path.startswith('selfIntroduction.motivation'):
            # 지원동기는 "회사의 주요 업무인 ○○는 제 경험과 맞닿아 있습니다"처럼 공고 업무를 회사 맥락으로
            # 쓰라고 지시한다(지시문 지원동기 규칙). 공고 용어를 새 기술어로 보면 그 수정안이 전부 버려진다.
            # 지원자 경험처럼 쓰는지는 이 검사가 아니라 역할·숫자 검사와 사용자 확인이 맡는다.
            allowed_terms |= grounding_terms(job_text)
        new_terms = grounding_terms(revision) - allowed_terms
        original_terms = grounding_terms(item.original_quote)
        # A user-confirmed replacement can legitimately restate the field without
        # repeating every token in the abbreviated original quote.
        # 다만 원문이 여러 문장이면 답 한 문장으로 통째 바꾸면서 답과 무관한 문장의 사실이 사라진다. 사용자가 원문 내용을
        # 되풀이해 답했을 때 원문 2문장(상황 + 숫자 결과)이 답 1문장으로 바뀌어 결과 숫자와 상황이 빠졌다(2026-09-15
        # 한 번도 안 본 케이스). 이 예외는 한 문장짜리 원문에만 둔다.
        answer_restates_revision = len(_sentences(item.original_quote)) <= 1 and any(
            revision.strip() and revision.strip() in answer.answer for answer in answers)
        # 답변을 근거로 문단을 새로 짠 내용 수정은 원문의 영단어를 모두 남길 필요가 없다("생성형 AI에
        # 관심" → 답변의 실제 업무로 바꿔 쓴 지원동기). 표현만 다듬는 수정은 계속 원문 사실을 지킨다.
        answer_text = "\n".join(answer_source_map.values())
        # 다만 문단 여러 문장을 통째로 갈아 끼우는 수정은 답과 무관한 문장의 사실까지 지운다. 2026-09-15 새 케이스에서
        # 원문 세 문장을 답변 두 문장으로 바꿔 FastAPI·Docker(공고 필수 요건)가 사라졌다. 면제는 한 문장짜리 원문에만 둔다.
        rebuilt_from_answer = (
            item.edit_type == 'content' and bool(answer_text)
            and _answer_is_reflected(item.original_quote, revision, answer_text)
            and len(_sentences(item.original_quote)) <= 1
        )
        missing_terms = set() if answer_restates_revision or rebuilt_from_answer else original_terms - grounding_terms(revision)
        # 원문 숫자가 수정안에서 사라진 것도 사실이 빠진 것이다. 영문 기술어만 보던 때는 "매물 500건을 한 번에 받던 것을"에서
        # 500건이 빠진 수정안이 통과했다(2026-09-15 새 케이스 v16m). 숫자는 예외 없이 본다. 답변 문장을 그대로 옮긴
        # 수정안이라도 원문의 숫자 결과가 사라지면 사실이 빠진 것이다(2026-09-15 한 번도 안 본 케이스).
        missing_numbers = _unsupported_numbers(item.original_quote, revision)
        # 이름·역할·기술 이름처럼 짧은 값을 담는 칸에 문장을 써 넣는 수정. "Fastlane"이 "Fastlane — ○○ 프로젝트 TestFlight
        # 배포 자동화, 40분 → 10분"이 됐다(2026-09-15). 답의 사실은 그 항목의 설명 칸에 들어가야 한다.
        if _NOMINAL_FIELD.fullmatch(item.field_path) and revision.strip() and (
                re.search(r'(습니다|했다|였다)\.?$', revision.strip()) or len(revision) > max(60, 2 * len(item.original_quote))
                # 기술 스택 이름 칸은 항목 하나에 이름 하나다. "Jest" → "Jest, supertest"처럼 이름을 덧붙이면 항목이 섞인다.
                or (item.field_path.startswith('techStack[') and grounding_terms(revision) - grounding_terms(item.original_quote))):
            item.validation_issues.append('nominal_field_rewritten')
        role_expansion = any(term in revision and term not in evidence for term in ROLE_EXPANSION_WORDS)
        if item.suggested_revision is not None and not revision.strip():
            item.validation_issues.append('empty_revision')
        if revision.strip():
            if _adds_duplicate_paragraph(original, revision):
                item.validation_issues.append('duplicate_existing_content')
            verbatim_copy, item.overlap_notice = _cross_field_overlap(item.field_path, item.original_quote, revision, fields)
            if verbatim_copy:
                item.validation_issues.append('copied_from_other_field')
            if not item.overlap_notice:
                item.overlap_notice = _repeated_facts_notice(item.field_path, item.original_quote, revision, fields)
            item.validation_issues.extend(_meaning_risks(item.original_quote, revision, answer_text))
            item.meaning_notice = _negation_notice(item.original_quote, revision, answer_text)
            if new_numbers:
                item.validation_issues.append('unsupported_number')
            if new_terms:
                item.validation_issues.append('unsupported_term')
            if missing_terms or missing_numbers:
                item.validation_issues.append('missing_fact_anchor')
            if role_expansion:
                item.validation_issues.append('unsupported_role')
            if ABSENCE_STATEMENT.search(revision) and not ABSENCE_STATEMENT.search(item.original_quote):
                item.validation_issues.append('absence_written')
            if uncertain_sentences:
                known = '\n'.join([*fields.values(), *answer_source_map.values(), item.original_quote])
                if any(_uncertain_fact_written(revision, sentence, known) for sentence in uncertain_sentences):
                    item.validation_issues.append('uncertain_fact_written')
            if '[연락처 삭제]' in revision or '[연락처 삭제]' in item.original_quote:
                item.validation_issues.append('redacted_content')
        if (not item.validation_issues and item.edit_type in _SURFACE_EDITS and revision.strip()
                and _is_minor_rewording(item.original_quote, revision)):
            # 사실 문제가 아니라 고칠 가치가 없는 수정이다. 확인 질문을 만들지 않고 수정안만 뺀다.
            item.suggested_revision = None
            warnings.append(f"사소한 표현 교체 수정안을 제외했습니다: {item.field_path}")
        if item.validation_issues:
            item.suggested_revision = None
            if 'duplicate_existing_content' in item.validation_issues:
                # Repeating an existing paragraph is not a missing-fact problem.
                item.confirmation_question = None
                warnings.append(f"기존 문단과 중복된 수정안을 제외했습니다: {item.field_path}")
            elif 'copied_from_other_field' in item.validation_issues:
                item.confirmation_question = None
                warnings.append(f"다른 칸 문장을 그대로 옮긴 수정안을 제외했습니다: {item.field_path}")
            elif item.edit_type in _SURFACE_EDITS and item.validation_issues == ['negation_changed']:
                # 표현만 다듬다 부정 표현("않도록" 등)이 흔들린 경우다. 원문은 사용자가 쓴 그대로이고 물을 사실이 없다.
                # 예전에는 "원문의 수행 여부와 수정안의 의미가 달라질 수 있습니다. 실제 수행 여부를 확인해 주세요."가
                # 질문으로 떠, 사용자는 무엇을 답할지 몰랐다(2026-09-15 자세한 이력서 목업).
                item.confirmation_question = None
            elif 'uncertain_fact_written' in item.validation_issues:
                # 사용자가 확신하지 못한다고 이미 답했다. 같은 것을 다시 묻지 않고 수정안만 버린다. 확인된 나머지 답은
                # 대체 수정안이 받는다.
                item.confirmation_question = None
            elif 'absence_written' in item.validation_issues:
                # 해 보지 않았다는 말을 이력서에 적으려던 수정안. 사용자는 이미 답했고 물을 것이 없다.
                item.confirmation_question = None
            elif 'nominal_field_rewritten' in item.validation_issues:
                # 짧은 칸에 문장을 쓰려던 수정안. 답할 것이 없으니 묻지 않는다(v16e에서 같은 칸에 질문이 세 턴 이어졌다).
                item.confirmation_question = None
            elif 'work_status_changed' in item.validation_issues:
                item.confirmation_question = "이 작업은 진행 중인가요, 완료된 상태인가요? 원문 상태를 바꿀 근거를 확인해 주세요."
            elif 'ownership_changed' in item.validation_issues or 'unsupported_role' in item.validation_issues:
                item.confirmation_question = "팀 전체의 작업과 구분하여 본인이 직접 맡은 범위를 알려 주세요."
            elif 'negation_changed' in item.validation_issues:
                # 부정 표현이 흔들린 내용 수정. 이 문구는 항목 이름도 바뀐 표현도 없어 답할 수 없고, 같은 칸을 세 턴 연속
                # 묻게 했다(2026-09-15 새 케이스). 수정안만 버리고 묻지 않는다. 원문은 사용자가 쓴 그대로다.
                item.confirmation_question = None
            elif item.validation_issues == ['missing_fact_anchor'] and answer_text:
                # 답변을 반영하다 원문 사실이 빠진 수정안. 사용자는 이미 답했고 원문 사실도 이력서에 그대로 있다. 이 질문은
                # 무엇을 답할지 알 수 없어 헛질문이 됐다. 수정안만 버리고, 답은 원문 사실을 살린 대체 수정안이 받는다.
                item.confirmation_question = None
            else:
                item.confirmation_question = "원문 의미를 유지하기 위해 직접 수행한 행동과 확인 가능한 결과를 알려 주세요. 수치는 없어도 됩니다."
            if 'duplicate_existing_content' not in item.validation_issues:
                warnings.append(f"문장 근거 검증 보류: {item.field_path}")
        item.evidence_quotes = quotes
        item.evidence_sources = [p for p, value in source_map.items() if any(q in value for q in quotes)]
        if revision.strip():
            item.evidence_sources.extend(
                source_path
                for source_path, answer_text in answer_source_map.items()
                if _answer_is_reflected(item.original_quote, revision, answer_text)
                and source_path not in item.evidence_sources
            )
        if item.suggested_revision is None:
            item.status = 'needs_confirmation' if item.confirmation_question else 'unchanged'
            if item.status == 'unchanged':
                item.edit_type = 'none'
        elif item.suggested_revision.strip() == item.original_quote.strip():
            item.status = 'unchanged'
            item.suggested_revision = None
            item.edit_type = 'none'
            if item.confirmation_question:
                item.status = 'needs_confirmation'
        elif re.sub(r'\s', '', item.suggested_revision) == re.sub(r'\s', '', item.original_quote):
            item.status = 'formatting'
            item.edit_type = 'spelling'
        else:
            item.status = 'formatting' if item.edit_type in ('spelling', 'tone', 'clarity') else 'improved'
            if item.edit_type == 'none':
                item.edit_type = 'content'
        if item.suggested_revision:
            item.fact_anchors = _fact_anchors(item.original_quote)
            item.change_rate = _change_rate(item.original_quote, item.suggested_revision)
            # A warning is informational only. The user still chooses whether to apply it.
            if item.change_rate > 0.3:
                item.change_rate_notice = '원문 대비 변경 폭이 큽니다. 적용 전 문장 의미와 사실 앵커를 다시 확인해 주세요.'
            spans.setdefault(item.field_path, []).append((start, end))
        valid.append(item)
    generation.sentence_reviews = valid
    # Legacy whole-section revisions have no field-level provenance: use sentence edits.
    for section in generation.section_reviews:
        section.suggested_revision = None
    return warnings


def _deduplicate(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in items if item and item.strip()))
