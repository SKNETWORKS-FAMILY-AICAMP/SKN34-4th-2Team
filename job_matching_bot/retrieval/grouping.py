"""같은 공고가 두 사이트에 올라온 것을 한 묶음으로 본다.

## 왜 필요한가

기업이 같은 공고를 사람인과 잡코리아에 함께 올린다. 번호가 다르고 본문 추출도
달라서 저장소에는 서로 다른 두 공고로 들어온다. 그대로 인덱스에 올리면 학생의
추천 목록에 **같은 공고가 두 번** 뜬다.

2026-09-21 실측: 상세를 받은 공고끼리 견줘 1,124쌍이 같은 공고였다. 목록까지 넣어
제목 완전일치로만 세도 잡코리아 공고의 19%에 사람인 짝이 있다.

## 무엇을 같다고 보는가

후보는 **같은 회사**로 좁힌다. 같은 공고는 반드시 회사가 같고, 회사당 공고가
중앙값 1건이라 견줄 짝이 확 줄어든다(전량 26만 번, 5초).

두 잣대 중 **하나만 맞으면** 같은 공고로 본다.

- 요건 구간(`documents.index_body`)의 낱말이 75% 넘게 겹친다
- 제목이 95% 넘게 닮았다 (「채용」 같은 꼬리말을 떼고 견준다)

본문 전체가 아니라 요건 구간만 보는 이유가 있다. 사람인은 「상세요강·복리후생」을,
잡코리아는 「회사 소개·홈페이지」를 붙이는데 그 껍데기가 본문의 절반이다. 같은
공고인데도 본문 전체 유사도가 0.36까지 떨어진다. 알맹이만 보면 글자까지 같다.

둘을 OR 로 거는 건 서로의 구멍을 메우기 때문이다. 잡코리아가 「상세내용을
입력하세요」만 써 둬 요건이 비어도 제목이 잡고, 회사가 제목을 아주 다르게 썼어도
요건이 잡는다. 목록만 있는 공고는 요건이 없으니 제목만으로 판정된다.

제목 정규화에서 **대괄호 안은 지우지 않는다.** 「[대구]」「[시스템플랫폼팀]」처럼
공고를 가르는 정보가 거기 들어간다. 지웠더니 지점이 다른 공고가 묶였다.

## 문턱을 왜 이렇게 잡았나

측정한 값이다(요건 자카드 0.75 이상을 정답으로 두고 제목 문턱을 훑었다).

    제목 0.85  잘못 묶음 183
    제목 0.90  잘못 묶음 150
    제목 0.95  잘못 묶음 113   ← 이걸 쓴다

**못 묶는 쪽으로 기운다.** 못 묶으면 목록에 같은 공고가 두 번 뜰 뿐이지만, 잘못
묶으면 대표가 아닌 쪽이 인덱스에서 빠져 **공고 하나가 사라진다.** 값이 다르다.

## 대표

묶음에서 요건 낱말이 가장 많은 공고를 대표로 쓴다. 사람인이 이미지 공고고
잡코리아가 글이면 잡코리아가 대표가 된다 — 첨삭이 인용할 문장이 많은 쪽이다.
같으면 `job_id` 순으로 정해 실행마다 흔들리지 않게 한다.

`group_key` 는 묶음에 속한 `job_id` 중 가장 앞선 것이다. 대표가 바뀌어도 값이
그대로라 화면이 기억한 주소가 깨지지 않는다.
"""

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from typing import Iterable

from job_matching_bot.retrieval import documents as doc
from job_matching_bot.schemas.job_posting import Job

# 요건 낱말이 이만큼 겹치면 같은 공고로 본다.
BODY_THRESHOLD = 0.75
# 제목이 이만큼 닮으면 같은 공고로 본다.
TITLE_THRESHOLD = 0.95
# 요건이 이보다 적으면 그 잣대는 쓰지 않는다. 몇 낱말로는 우연히 겹친다.
MIN_BODY_TOKENS = 12
# 요건으로 묶을 때 제목이 최소한 이만큼은 닮아야 한다.
#
# 자격요건 문구를 모든 공고에 똑같이 박아 두는 회사가 있다. 비상교육이 그랬다 —
# 「GPU 최적화 엔지니어」와 「유초등 영어 프랜차이즈 교육기획」이, 「DevSecOps 리드」와
# 「UX 리서처」가 요건이 같다는 이유로 짝이 됐다. 그런 회사에서는 요건이 아무것도
# 말해 주지 않으므로 제목이 받쳐 줘야 한다.
TITLE_FLOOR = 0.5
# 회사 안의 공고가 이보다 많으면 묶지 않는다. 헤드헌팅 업체가 비슷한 제목을 대량으로
# 올리는데, 거기서 묶기 시작하면 수십 건이 한 덩어리가 되어 대부분이 검색에서 빠진다.
MAX_COMPANY_JOBS = 60

_COMPANY_NOISE = re.compile(r"주식회사|㈜|\(주\)|주\)|inc|corp|co\.?,?\s*ltd")
_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_NON_WORD = re.compile(r"[^0-9a-z가-힣]")
# 제목에서 떼는 말. **"이것은 채용공고다"라는 뜻뿐인 말만** 뗀다.
#
# 처음에는 「신입」「경력」「정규직」「계약직」도 뗐는데, 그것들이 공고를 가르는
# 정보였다. 심스리얼리티의 `SW개발자 정규직 모집 (경력 3년이상)` 과 `(경력 5년이상)`,
# `신입 계약직 모집` 이 떼고 나면 거의 같은 글자가 되어 셋이 한 묶음이 됐다.
_TITLE_TAIL = re.compile(
    r"채용공고|공개채용|수시채용|상시채용|채용|모집|공고|구인|영입|충원|각부문|부문별"
)
_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")


def normalize_company(name: str) -> str:
    """회사명에서 괄호와 법인격을 걷어낸다."""
    text = _BRACKETS.sub(" ", (name or "").lower())
    return _NON_WORD.sub("", _COMPANY_NOISE.sub(" ", text))


def normalize_title(title: str) -> str:
    """제목에서 모집 구분만 뗀다. **대괄호 안은 남긴다** — 지점·부서가 거기 있다."""
    return _TITLE_TAIL.sub("", _NON_WORD.sub("", (title or "").lower()))


def body_tokens(job: Job) -> set[str]:
    """요건 구간의 낱말. 인덱스에 올라가는 것과 같은 글을 본다."""
    return set(_TOKEN.findall(doc.index_body(job).lower()))


def match_score(left: Job, right: Job, tokens: dict[str, set[str]]) -> float:
    """두 공고가 얼마나 같은 공고 같은가. 0이면 짝이 아니다.

    **한 사이트 안끼리는 견주지 않는다.** 그건 `dedup.find_reposts` 의 일이고, 거기에는
    여기서 쓸 수 없는 방어가 들어 있다 — 지역이 다르면 지점 분리, 경력 조건이 다르면
    연차 분리로 보고 안 묶는다. 그 두 값은 사이트마다 적는 방식이 달라 사이트를
    가로질러서는 못 쓴다(맞춰 보면 재현율이 0이다).

    그 방어 없이 한 사이트 안을 묶었더니 이렇게 됐다. 한샘 38건(지점별 디자이너
    모집), 위쉬정보기술 33건(SI 프로젝트별), 스카우트플랜 31건(헤드헌팅). 자격요건
    문구가 같아서 붙은 것이지 같은 공고가 아니다.
    """
    if left.source == right.source:
        return 0.0
    a, b = tokens[left.job_id], tokens[right.job_id]
    body = 0.0
    if len(a) >= MIN_BODY_TOKENS and len(b) >= MIN_BODY_TOKENS:
        body = len(a & b) / len(a | b)
    title = difflib.SequenceMatcher(
        None, normalize_title(left.title), normalize_title(right.title)
    ).ratio()
    if title >= TITLE_THRESHOLD:
        return max(body, title)
    if body >= BODY_THRESHOLD and title >= TITLE_FLOOR:
        return max(body, title)
    return 0.0


def plan(jobs: Iterable[Job]) -> tuple[dict[str, str], set[str]]:
    """({job_id: group_key}, 대표 job_id 집합).

    요건 낱말은 공고마다 한 번만 만든다. 4만 건에 30초쯤 걸리는 일이라 두 번 하면 그만큼 는다.
    """
    jobs = list(jobs)
    tokens = {job.job_id: body_tokens(job) for job in jobs}
    parent = {job.job_id: job.job_id for job in jobs}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        a, b = find(left), find(right)
        if a != b:
            # 늘 작은 쪽을 뿌리로 둬야 group_key 가 실행마다 같다.
            parent[max(a, b)] = min(a, b)

    by_company: dict[str, list[Job]] = defaultdict(list)
    for job in jobs:
        by_company[normalize_company(job.company)].append(job)

    # **무리 짓기가 아니라 1:1 짝짓기다.** A와 B가 닮고 B와 C가 닮으면 무리 짓기는
    # 셋을 한 덩어리로 만든다. 그래서 큐픽스의 주간·야간·목~월 세 공고가, 심스리얼리티의
    # 3년·5년·신입 세 공고가 한 묶음이 됐다. 사이트마다 짝은 **하나씩**이다.
    #
    # 점수가 높은 짝부터 채운다. 3년짜리에는 반대편 3년짜리가 1.00으로 더 잘 맞으므로
    # 5년짜리와 0.95로 붙기 전에 제자리를 찾는다.
    candidates: list[tuple[float, str, str]] = []
    for company, rows in by_company.items():
        if not company or len(rows) < 2 or len(rows) > MAX_COMPANY_JOBS:
            continue
        for i, left in enumerate(rows):
            for right in rows[i + 1:]:
                score = match_score(left, right, tokens)
                if score:
                    candidates.append((score, left.job_id, right.job_id))

    # 점수 내림차순. 같으면 job_id 순 — 실행마다 같은 답이 나와야 한다.
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    source_of = {job.job_id: job.source for job in jobs}
    taken: set[tuple[str, str]] = set()      # (job_id, 상대 사이트)
    for _, left, right in candidates:
        slot_left = (left, source_of[right])
        slot_right = (right, source_of[left])
        if slot_left in taken or slot_right in taken:
            continue
        taken.add(slot_left)
        taken.add(slot_right)
        union(left, right)

    groups = {job.job_id: find(job.job_id) for job in jobs}

    # 묶음마다 요건 낱말이 가장 많은 공고. 같으면 job_id 가 앞선 쪽 — 실행마다 같아야 한다.
    best: dict[str, Job] = {}
    for job in jobs:
        key = groups[job.job_id]
        champ = best.get(key)
        if champ is None:
            best[key] = job
            continue
        mine, theirs = len(tokens[job.job_id]), len(tokens[champ.job_id])
        if mine > theirs or (mine == theirs and job.job_id < champ.job_id):
            best[key] = job

    return groups, {job.job_id for job in best.values()}
