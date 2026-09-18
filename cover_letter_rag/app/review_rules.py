"""첨삭 검증이 여러 곳에서 함께 쓰는 이력서 칸 이름과 낱말 목록.

같은 목록을 review_workflow·resume_review·star_checks에 따로 적어 두면, 한쪽만 고쳤을 때 규칙이 서로 어긋난다
(2026-09-15 정리 전: 경험 칸 정규식 7곳, 칸 이름표 2벌, 항목 이름 키 2벌, 역할 과장 낱말 2벌). 목록은 여기서만 고친다.
"""
import re

# 경험을 적는 목록 칸. 항목마다 이름 칸과 설명(description) 칸이 있다.
EXPERIENCE_SECTIONS = ('projects', 'experience', 'awards', 'otherActivities', 'trainingExperience')
EXPERIENCE_SECTION_PATTERN = '|'.join(EXPERIENCE_SECTIONS)

# 항목 이름이 들어 있는 칸. 경력은 회사, 교육은 과정 이름이 항목 이름이다.
ITEM_NAME_KEYS = {'projects': 'name', 'experience': 'company', 'trainingExperience': 'course',
                  'awards': 'name', 'otherActivities': 'name'}

# "projects[2]"처럼 경험 항목을 가리키는 경로의 앞부분. 묶음은 (칸, 번호).
EXPERIENCE_ITEM = re.compile(rf'({EXPERIENCE_SECTION_PATTERN})\[(\d+)\]')
# 경험 항목의 설명 칸. 묶음은 (칸, 번호).
EXPERIENCE_DESCRIPTION = re.compile(rf'({EXPERIENCE_SECTION_PATTERN})\[(\d+)\]\.description')
# 문장으로 적는 칸: 핵심역량, 경험 설명, 자기소개서 문항 본문.
NARRATIVE_FIELD = re.compile(
    rf'coreCompetencies\.text|(?:{EXPERIENCE_SECTION_PATTERN})\[\d+\]\.description|selfIntroduction\.[^.]+\.body'
)


def noun_fragment_sentences(text: str) -> list[str]:
    """명사형으로 끊긴 문장("사내 관리자 페이지의 Django REST API 유지보수.", "정확도 0.87.", "만들었음.").

    마지막 글자가 서술 어미(다·요)가 아닌 문장이다. 끊긴 문장과 온전한 문장이 한 칸에 섞이면 모델이 칸 전체를
    "이미 괜찮다"고 보고 건너뛰어, 개발용 30칸 중 25~26칸만 이었다(2026-09-15 v16n·v16p). 모델에 목록으로 준다.
    """
    sentences = []
    for part in re.split(r'(?<=\.)\s+|\n+', str(text or '')):
        body = part.strip().rstrip('.').rstrip()
        if len(body) >= 4 and body[-1] not in '다요!?':
            sentences.append(part.strip())
    return sentences


# STAR 행동 확인. 모델이 "데이터 수집과 시각화를 맡았습니다", "개발을 본격적으로 배웠습니다"를 행동으로 봤다.
# 역할·참여·학습 말만 있고 무엇을 어떻게 했는지(방법) 말이 없으면 행동이 아니다.
# 결과 쪽 낱말 확인도 만들어 봤지만 버렸다: 개발용 기록에서는 일치가 올랐는데, 최종 확인용 기록에서 "0으로
# 만들었습니다", "0.81에서 0.87로 올렸습니다"를 결과로 못 알아봐 54/58 → 48/58로 떨어졌다(2026-09-15).
STAR_ROLE_ONLY = re.compile(r'맡았|맡아|담당|참여|배웠|학습|공부|익혔|관심|흥미')
STAR_ACTION_CUE = re.compile(
    r'적용|구현|작성|만들|만든|개발했|개발하|설계|도입|분석|수집해|수집했|정리해|정리했|나누|나눠|바꾸|바꿔|바꿨|추가|자동화|'
    r'측정|튜닝|옮기|옮겨|연동|구축했|구축하|수정|찾아|쌓아|읽고|읽어|확인하|테스트|검증하|붙였|붙여|잡고|잡아|계산|'
    r'파싱|정규화|제거|전환|리팩터|캐시|인덱스|개선했|배포|학습시켰|시도|남기|남겼|물어보|대화로'
)


def star_action_quote_has_method(quote: str) -> bool:
    """행동 인용이 역할·학습 말만으로 되어 있지 않은가."""
    if not STAR_ROLE_ONLY.search(quote or ''):
        return True
    return bool(STAR_ACTION_CUE.search(STAR_ROLE_ONLY.sub('', quote)))


# 해 보지 않았다는 말. 이력서는 한 일만 적는 문서라 수정안에 새로 들어가면 안 된다(지시문 22번). 답이 "개념만 배웠고
# 실제로 써 본 적은 없다"였는데 핵심역량 수정안이 원문 문장을 지우고 그 말을 적었다(2026-09-15 한 번도 안 본 케이스).
# 답에 있는 말을 옮긴 것이라 부정 표현 검사("답변에 있는 표현")를 지나갔다.
ABSENCE_STATEMENT = re.compile(
    r'(?:써|사용해|다뤄|적용해|해)\s*본\s*(?:적|경험)(?:은|이|도)?\s*없|경험(?:은|이|도)?\s*없|'
    r'개념(?:만|\s*위주로)|이론(?:만|으로만)|수업에서만|강의로만|'
    # "만들어 보지 않았어요", "안 써 봤어요". 예전에는 써·사용해·다뤄·적용해 네 낱말만 봐서 답을 그대로 붙이는 대체
    # 수정안에 "만들어 보지 않았어요"가 들어갔다(2026-09-15 한 번도 안 본 케이스, 사람 말투 답).
    r'[가-힣]\s*보지\s*(?:는|도)?\s*(?:않|못)|안\s*(?:해|써|만들어|다뤄|사용해|적용해)\s*봤'
)


# 확신하지 못한 답. "~했던 것 같아요", "잘 모르겠는데 아마 30개쯤"으로 답한 내용이 수정안에서 단정문이 됐다(2026-09-15
# 한 번도 안 본 케이스, 사람 말투 답 7턴 중 2턴). 서버는 그 사실이 맞는지 알 수 없으니 확인된 근거로 쓰지 않는다.
# "느린 것 같아서 인덱스를 추가했어요"의 "것 같아서"는 이유라 확신 여부와 상관없어 뺀다. "모르겠"만으로는 잡지 않는다
# ("수치는 모르겠는데 캐시는 붙였어요"의 캐시는 확인된 사실이다).
UNCERTAIN_STATEMENT = re.compile(
    r'것\s*같(?!아서|았)|듯\s*(?:해요|합니다|하다|싶|한데|하고)|(?:^|\s)아마(?:도)?\s|'
    r'(?:확실|정확)(?:하지|치|하진)\s*(?:는\s*)?않|정확히는?\s*모르|'
    r'기억(?:이|은|상)?\s*(?:잘\s*)?(?:안\s*나|나지\s*않)|가물가물|헷갈|어렴풋'
)
_ANSWER_SENTENCE_BREAK = re.compile(
    r'(?<=[.!?])\s+|\n+|(?<=같고)[,\s]+|(?<=같은데)[,\s]+|(?<=같아요)[,\s]+|(?<=같습니다)[,\s]+'
)


def split_uncertain_answer(text: str) -> tuple[str, list[str]]:
    """답을 확인된 부분과 확신하지 못한 문장들로 나눈다. 확신하지 못한 문장이 없으면 답을 그대로 돌려준다."""
    text = str(text or '')
    sentences = [part.strip() for part in _ANSWER_SENTENCE_BREAK.split(text) if part and part.strip()]
    uncertain = [sentence for sentence in sentences if UNCERTAIN_STATEMENT.search(sentence)]
    if not uncertain:
        return text, []
    return ' '.join(sentence for sentence in sentences if sentence not in uncertain), uncertain


# 사용자에게 보이는 칸 이름. 내부 경로("coreCompetencies.text")를 문장에 쓰지 않을 때 쓴다.
SECTION_NAMES = {'coreCompetencies': '핵심역량', 'selfIntroduction': '자기소개서', 'trainingExperience': '교육',
                 'otherActivities': '활동', 'techStack': '기술 스택', 'projects': '프로젝트', 'experience': '경력',
                 'awards': '수상', 'certifications': '자격증', 'education': '학력', 'basicInfo': '기본 정보'}

# 근거 없이 수정안에 새로 들어가면 역할을 부풀린 것으로 보는 낱말.
ROLE_EXPANSION_WORDS = ('주도', '총괄', '리드', '책임', '달성')

# 항목 이름에 흔히 붙어 어느 항목인지 가려 주지 못하는 낱말.
GENERIC_NAME_TOKENS = {'개발', '서비스', '시스템', '프로젝트', '기반', '관리', '구축', '과정', '교육', '참여', '팀',
                       '웹', '앱', '플랫폼', '구현', '활동', '동아리', '수상', '대회', '주식회사', '(주)'}
# 새 프로젝트 이름에 흔히 붙어 사실을 담지 않는 낱말. 이름이 답에 있는 말인지 볼 때 세지 않는다.
NEW_PROJECT_NAME_GENERIC = GENERIC_NAME_TOKENS | {'과제', '개인', '토이', '사이드', '화면', '기능', '페이지', '연동', '만들기'}
# 프로젝트 이름이 이 낱말로만 되어 있으면 무엇을 만들었는지 없이 형태만 적힌 이름이다.
PROJECT_FORM_WORDS = {'부트캠프', '개인', '과제', '토이', '사이드', '프로젝트', '수업', '학교', '동아리', '팀', '졸업', '캡스톤',
                      '미니', '실습', '교육', '과정', '팀프로젝트', '개인과제'}

# 부정 표현. 원문과 수정안 사이에서 생기거나 사라지면 뜻이 바뀌었을 수 있다.
NEGATION = r'않|못|없|아니|미완료|미구현'
# 한 일 자체를 부정하는 표현. 뒤집히면 하지 않은 일을 한 것처럼 쓰게 되니 계속 막는다.
WORK_NEGATION = re.compile(
    r'않았|못|없었|아니었|미완료|미구현|(?:경험|사용한\s*적|해\s*본\s*적|써\s*본\s*적)(?:은|이)?\s*없'
)
# "없"·"아니"·"못"이 들어 있지만 부정이 아닌 낱말. "끊임없이 배우고 성장하겠습니다"를 부정으로 잡아 안내가 붙었다
# (2026-09-15 새 케이스 v16m). 부정 검사 전에 지운다.
NOT_NEGATION_WORDS = re.compile(
    r'끊임\s*없|어김\s*없|틀림\s*없|빠짐\s*없|거침\s*없|아낌\s*없|쉴\s*새\s*없|빈틈\s*없|변함\s*없|다름\s*없|손색\s*없|'
    r'하염\s*없|상관\s*없|관계\s*없|뿐(?:만)?\s*아니|못지\s*않|마지\s*않'
)
