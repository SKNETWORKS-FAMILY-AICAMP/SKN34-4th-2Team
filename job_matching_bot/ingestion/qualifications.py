"""자격요건 구간에서 전공·자격증·병역 조건을 뽑는다.

자격요건 줄의 73%가 학력·전공, 10%가 자격증·어학, 16%가 병역·결격 사유를 말한다.
이력서에는 전공(학력사항)과 자격사항이 있으니 비교할 수 있는데, 지금까지는 경력·학력만
봤다. 여기서 뽑은 값은 Job에 실려 하드 필터 세 곳(hard_filter.py / local_job_matcher.dart /
jobCoach.ts)이 같은 규칙으로 통과·확인 필요를 판정한다.

원칙: 공고에 적혀 있고 이력서와 맞으면 통과, 맞는지 확인할 수 없으면 확인 필요.
"관련 전공"처럼 경계가 흐린 요건은 불일치로 탈락시키지 않는다.

전공은 사람이 읽는 표시명(`majors`)과, 이력서 전공 문자열에 부분 일치시킬 정규화
용어(`major_terms`)를 따로 둔다. 매처는 용어 목록만 부분 일치시키면 되므로 세 언어에
전공 사전을 복제하지 않아도 된다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 표시명 → (공고 줄에서 이 그룹을 알아보는 단서, 이력서 전공에 부분 일치시킬 용어)
MAJOR_GROUPS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "컴퓨터·소프트웨어": (
        ("컴퓨터", "전산", "소프트웨어", "정보통신", "정보보호", "정보시스템", "정보공학", "컴공", "인공지능", "데이터"),
        ("컴퓨터", "전산", "소프트웨어", "정보통신", "정보보호", "정보시스템", "정보공학", "컴공", "인공지능", "데이터", "ai"),
    ),
    "전자·전기": (
        ("전자", "전기", "반도체", "제어", "통신공학"),
        ("전자", "전기", "반도체", "제어", "통신"),
    ),
    "통계·수학": (
        ("통계", "수학", "수리"),
        ("통계", "수학", "수리"),
    ),
    "산업·경영공학": (
        ("산업공학", "산업경영", "경영정보", "mis"),
        ("산업공학", "산업경영", "경영정보", "mis"),
    ),
    "기계·자동차": (
        ("기계", "자동차", "메카트로닉스"),
        ("기계", "자동차", "메카트로닉스"),
    ),
    "이공계": (
        ("이공계", "공학계열", "이과", "자연과학", "공대"),
        ("공학", "과학", "이학", "컴퓨터", "전산", "소프트웨어", "전자", "전기", "수학", "통계", "물리", "화학", "기계"),
    ),
}

_MAJOR_CONTEXT = re.compile(r"전공|학과|계열|학사|졸업")
_MAJOR_ANY = re.compile(r"(전공|학과|학력)\s*(무관|불문)|무관")

CERTIFICATIONS: tuple[str, ...] = (
    "정보처리기사", "정보처리산업기사", "정보보안기사", "정보보안산업기사", "네트워크관리사",
    "리눅스마스터", "빅데이터분석기사", "데이터분석준전문가", "데이터분석전문가",
    "SQLD", "SQLP", "ADsP", "ADP", "DAsP", "DAP",
    "AWS Certified", "AWS SAA", "CCNA", "CCNP", "PMP", "CISA", "CISSP",
    "컴퓨터활용능력", "워드프로세서", "전기기사", "산업안전기사", "일반기계기사",
    "OPIc", "OPIC", "TOEIC", "토익", "토스", "TOEIC Speaking", "TEPS", "JLPT", "HSK",
    "TOEFL", "토익스피킹", "토플",
)

# 어학 성적. 자격증과 성격이 다르므로 따로 담는다.
#
# 자격요건에서 자격증이 잡힌 모집 중 공고 669건 중 **361건(54%)이 어학 성적뿐이었다.**
# OPIc 301건, TOEIC 203건이 가장 많다. 그런데 앱 이력서의 자격사항 칸에 토익 점수를
# 적는 사람은 드물다. 이걸 자격증으로 취급해 조건을 걸면, 이력서에 안 적었다는 이유로
# 멀쩡한 지원자가 걸린다.
#
# 점수 기준도 다르다. 자격증은 있고 없고지만 어학은 "TOEIC 700점 이상"처럼 문턱이 있다.
# 지금 구조로는 그 숫자를 비교할 수 없다. 그래서 조건으로 쓰지 않고 보여 주기만 한다.
LANGUAGE_TESTS: frozenset[str] = frozenset(
    {"OPIc", "OPIC", "TOEIC", "토익", "토스", "TOEIC Speaking", "토익스피킹",
     "TEPS", "TEP", "JLPT", "HSK", "TOEFL", "토플"}
)
_CERT_CONTEXT = re.compile(r"자격|기사|certified|opic|toeic|토익|토스|teps|jlpt|hsk|sqld|adsp", re.IGNORECASE)
_GENERIC_GISA = re.compile(r"([가-힣A-Za-z]{2,12}(?:산업)?기사)")
# `~기사`로 끝나지만 자격증이 아닌 말. 사람을 가리키거나(운전기사·배송기사) 글을
# 가리킨다(홍보기사). 이걸 필수 자격증으로 잡으면 지원 가능한 사람이 탈락한다.
_NOT_A_CERTIFICATE = frozenset({
    "운전기사", "배송기사", "납품기사", "수행기사", "임원수행기사", "현장기사",
    "홍보기사", "설치보조기사", "공사기사", "보조기사", "담당기사", "출장기사",
    # 앞말이 잘려 나온 조각. 온전한 이름이 따로 잡히므로 버려도 잃는 것이 없다.
    "처리기사", "측정기사", "진단기기사", "대기환기사", "안전산업기사", "보안기사",
})
# 예시로 든 문장. "정보처리기사 등 IT 관련 자격증 보유"는 그 자격증이 **필수**라는
# 뜻이 아니다. 363건 중 21건(6%)이 이 모양이다. 탈락 조건으로 쓰면 안 된다.
_EXAMPLE_LINE = re.compile(
    r"등\s*(?:[가-힣A-Za-z]{1,6}\s*){0,3}자격|예\s*[:：]|중\s*택|이에\s*준하는"
)
# 한 줄에 여러 자격증이 나올 때 "이 중 하나"를 뜻하는 표시.
_CERT_ALL = re.compile(r"및\s|모두\s*(?:보유|소지)|전부\s*(?:보유|소지)|둘\s*다")
# 경력 연차. "경력 5년 이상", "3년 이상 10년 이하", "5~10년", "경력 : 3년".
# 숫자 앞에 숫자가 없어야 하므로 "2026년"은 잡히지 않고, "2년제"·"3년차"는 뒤 글자로 거른다.
# "경력 3년 이하"는 상한이지 요구가 아니다.
_YEARS_MIN = re.compile(r"(?<!\d)(\d{1,2})\s*(?:~\s*\d{1,2}\s*)?년\s*(?:이상|↑)")
_YEARS_LABELED = re.compile(
    r"(?:경력|실무|경험)\s*:?\s*(?<!\d)(\d{1,2})\s*(?:~\s*\d{1,2}\s*)?년(?![제차])(?!\s*(?:이하|미만))"
)
_CAREER_REQUIRED = re.compile(r"경력자|유경험자|경력\s*필수|경력\s*보유자")
# 이 말이 있으면 신입도 받는다는 뜻이다. 그 줄의 연차는 요구가 아니라 다른 직무의 조건이다.
_ENTRY_MENTION = re.compile(r"신입|경력\s*무관|인턴|초보")
_MILITARY = re.compile(r"병역|군필|군\s*복무")
_MILITARY_DONE = re.compile(r"필|면제|마친|완료")


@dataclass
class Qualifications:
    majors: list[str] = field(default_factory=list)
    major_terms: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    # "이 중 하나면 된다"로 묶은 자격증. 각 묶음에서 하나만 맞으면 충족이다.
    # `certifications`는 화면에 보여 줄 평평한 목록이고, 판정은 이쪽을 본다.
    certification_groups: list[list[str]] = field(default_factory=list)
    # 어학 성적. 조건으로 걸지 않고 보여 주기만 한다. LANGUAGE_TESTS 설명 참고.
    language_tests: list[str] = field(default_factory=list)
    military_required: bool = False
    # 자격요건이 요구하는 최소 연차. 여러 직무면 가장 낮은 값 — 문턱이 낮은 자리 기준이어야
    # 억울한 탈락이 없다. 연차 없이 "경력자"라고만 쓰면 career_required 만 켜진다.
    min_career_years: int | None = None
    career_required: bool = False
    # 요건 줄에서 신입을 언급했는가. 정규화 단계가 제목과 합쳐 판단한다.
    mentions_entry: bool = False
    evidence: dict[str, list[str]] = field(
        default_factory=lambda: {
            "majors": [], "certifications": [], "language_tests": [], "military": [], "career": []
        }
    )


def normalize_term(text: str) -> str:
    """공백·기호를 지우고 소문자로. 매처 세 곳이 같은 정규화를 쓴다."""
    return re.sub(r"[\s\-_/·.()\[\]]", "", text).lower()


def extract_qualifications(lines: list[str], *, preferred: bool = False) -> Qualifications:
    """구간의 줄 목록에서 전공·자격증·병역 조건을 뽑는다.

    기본은 **자격요건 구간**이다. 그 안에 섞여 든 '우대' 줄은 건너뛴다.

    `preferred=True`는 **우대사항 구간**을 읽을 때다. 두 가지가 달라진다.

    - '우대'라는 글자로 거르지 않는다. 그 구간은 원래 다 우대다.
    - **전공과 자격증만 담는다.** 연차·병역은 없어도 지원할 수 있는 것이 아니므로
      우대사항에서 끌어오면 안 된다. 그걸 조건으로 걸면 우대 한 줄 때문에 지원
      가능한 공고가 사라진다.

    우대 자격증·전공은 아직 순위에 쓰지 않는다. 지금은 화면과 채점에 보여
    쓸모가 있는지 재기 위한 것이다.
    """
    result = Qualifications()
    seen_groups: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or (not preferred and "우대" in line):
            continue
        lowered = line.lower()

        if _MAJOR_CONTEXT.search(line) and not _MAJOR_ANY.search(line):
            for name, (cues, terms) in MAJOR_GROUPS.items():
                if name in seen_groups:
                    continue
                if any(cue.lower() in lowered for cue in cues):
                    seen_groups.append(name)
                    result.majors.append(name)
                    for term in terms:
                        normalized = normalize_term(term)
                        if normalized not in result.major_terms:
                            result.major_terms.append(normalized)
                    result.evidence["majors"].append(line)

        if _CERT_CONTEXT.search(line):
            found: list[str] = []
            for cert in CERTIFICATIONS:
                if normalize_term(cert) in normalize_term(line):
                    found.append(cert)
            for match in _GENERIC_GISA.findall(line):
                if not any(normalize_term(match) in normalize_term(c) or normalize_term(c) in normalize_term(match) for c in found):
                    found.append(match)

            # 어학 성적은 따로 담는다. 조건으로 걸 수 없는 것이라 섞으면 안 된다.
            langs = [c for c in found if c in LANGUAGE_TESTS]
            certs = [
                c for c in found
                if c not in LANGUAGE_TESTS and c not in _NOT_A_CERTIFICATE
            ]
            # "~ 등 관련 자격증"은 예시다. 필수로 걸면 지원 가능한 사람이 탈락한다.
            if _EXAMPLE_LINE.search(line):
                certs = []

            for name in langs:
                if not any(normalize_term(name) == normalize_term(c) for c in result.language_tests):
                    result.language_tests.append(name)
            if langs:
                result.evidence["language_tests"].append(line)

            fresh: list[str] = []
            for cert in certs:
                if not any(normalize_term(cert) == normalize_term(c) for c in result.certifications):
                    result.certifications.append(cert)
                fresh.append(cert)
            if certs:
                result.evidence["certifications"].append(line)
                # 한 줄에서 나온 자격증은 **이 중 하나**면 된다. 묶어 두지 않으면
                # 매처가 하나씩 따로 검사해, 자격을 갖춘 사람이 나머지를 안 가졌다는
                # 이유로 걸린다.
                #
                # "또는"이 있는 줄이 51%다. 나머지도 마찬가지였다. 쉼표로 나열한 99개
                # 줄을 전부 읽어 보니 "정보처리기사, 네트워크관리사, 리눅스마스터 등",
                # "CCNA/CCNP/CCIE 등", "실내건축기사, 실내건축산업기사"처럼 다 대안이었다.
                # **둘 다 가지라는 공고는 하나도 없었다.** 그래서 기본이 "이 중 하나"다.
                # `및`·`모두`처럼 함께 요구하는 표시가 있을 때만 각각으로 나눈다.
                if fresh:
                    # 이미 다른 묶음에 든 것은 빼고 새로 묶는다. 같은 자격증이 두 묶음에
                    # 들어가면 하나만 가진 사람이 "나머지를 안 가졌다"고 걸린다.
                    taken = {normalize_term(c) for g in result.certification_groups for c in g}
                    group = [c for c in fresh if normalize_term(c) not in taken]
                    if not group:
                        pass
                    elif len(group) > 1 and _CERT_ALL.search(line):
                        result.certification_groups.extend([c] for c in group)
                    else:
                        result.certification_groups.append(group)

        if preferred:
            continue

        if _MILITARY.search(line) and _MILITARY_DONE.search(line) and "무관" not in line:
            result.military_required = True
            result.evidence["military"].append(line)

        if _ENTRY_MENTION.search(line):
            result.mentions_entry = True
        else:
            years = [int(m.group(1)) for m in _YEARS_MIN.finditer(line)]
            years += [int(m.group(1)) for m in _YEARS_LABELED.finditer(line)]
            years = [y for y in years if 1 <= y <= 20]
            if years:
                low = min(years)
                if result.min_career_years is None or low < result.min_career_years:
                    result.min_career_years = low
                result.evidence["career"].append(line)
            elif _CAREER_REQUIRED.search(line):
                result.career_required = True
                result.evidence["career"].append(line)
    return result
