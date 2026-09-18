"""후보를 LLM에 넘기기 전에 다시 세운다 — 벡터 순위와 기술 겹침을 섞어서.

## 왜 필요한가

벡터 검색이 매긴 순서는 후보 안에서 거의 평평하다. 6개 이력서로 재 보니 후보 12~17건의
유사도 폭이 0.042~0.140뿐이었다. 그 좁은 구간의 순서로 "누구를 먼저 보여줄지"와
"누구를 LLM에 보낼지"를 정하고 있었다.

기술 겹침은 훨씬 넓게 흩어지고(0~67%), LLM이 매긴 적합도와도 깨끗하게 이어진다.
후보 79건을 전부 판정시켜 본 결과다.

    높음 30% · 보통 19% · 낮음 10%   (적합도별 평균 겹침)

판정과의 순위상관도 기술 겹침(+0.33)이 벡터 순위(+0.26)보다 높았다. 둘을 반씩 섞으면
+0.42로 올라간다 — 어느 한쪽만 쓸 때보다 낫다. 가중치는 0.4~0.7 구간이 고르게 좋아서
가운데인 0.5로 둔다. 표본이 6개 이력서라 소수점까지 맞추는 것은 과적합이다.

## 정보가 없는 공고를 벌주지 않는다

인덱스에 올라간 공고의 **53%가 기술 정보를 아예 안 갖고 있다.** 겹침을 0으로 치면
"정보 없음"이 "안 맞음"이 되어 그 공고들이 통째로 뒤로 밀린다. 그래서 정보가 없는
공고는 그 요청의 평균 겹침으로 두어 **제자리에 남긴다.** 근거가 없으면 움직이지 않는
것이 맞다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, TypeVar

from job_matching_bot.ingestion.qualifications import normalize_term
from job_matching_bot.ingestion.requirement_sections import split_sections
from job_matching_bot.ingestion.saramin_tech_vocab import find_tech_in_text
from job_matching_bot.matching.skill_normalize import canonical_set
from job_matching_bot.schemas.job_posting import Job

# 기술 겹침에 줄 비중. 나머지는 벡터 유사도 몫이다.
SKILL_WEIGHT = 0.5

# 공고가 우대한다고 적은 자격증·전공을 이력서가 가졌을 때 얹는 몫.
#
# 우대사항은 없어도 지원에 지장이 없다. 그래서 **더하기만 하고 빼지 않는다.** 우대
# 요건이 아예 없는 공고(표본의 약 89%)와, 있지만 못 맞춘 공고는 똑같이 0을 받는다.
# 못 맞췄다고 뒤로 밀면 그건 조건으로 거는 것이지 우대가 아니다.
#
# 값이 작다. 기술 겹침(0.5)의 십분의 일이다. 순위를 뒤집는 힘이 아니라 비슷할 때
# 앞에 세우는 정도다. 사람이 매긴 43건에서 우대 요건이 맞은 경우가 5건뿐이라
# 효과를 재지 못했다. 이 숫자는 측정한 값이 아니라 "작게 두자"는 판단이다.
BONUS_WEIGHT = 0.05


@dataclass(frozen=True)
class SkillMatch:
    """공고가 요구하는 기술 중 이력서가 가진 것."""

    matched: tuple[str, ...]
    pool_size: int
    # 태그가 없어 요건 구간 글에서 찾은 기술로 쟀는가.
    from_body: bool = False

    @property
    def coverage(self) -> float | None:
        """겹친 비율. 공고에 기술 정보가 없으면 None — 0이 아니다."""
        if self.pool_size == 0:
            return None
        return len(self.matched) / self.pool_size


def skill_match(job: Job, resume_skills: Sequence[str]) -> SkillMatch:
    """공고의 요구 기술과 이력서 기술을 표준 키로 맞대어 본다.

    `required_skills`와 `tech_stack`을 합쳐서 본다. 전자는 본문에서 뽑은 요건이고
    후자는 기업이 등록한 태그인데, 저장소에서 각각 26%·35%만 채워져 있어 한쪽만
    보면 볼 수 있는 공고가 절반으로 줄어든다.

    둘 다 비었으면 요건 구간(자격요건·우대사항·주요업무) 글에서 태그와 같은 어휘로
    찾는다. 기술 정보가 없는 OPEN 공고 22,383건 중 5,276건이 이렇게 채워지고, 공고당
    0.5ms라 요청 시간에는 티가 안 난다. 글에도 없으면 그대로 "정보 없음"이다 — 제자리에 둔다.
    """
    pool = canonical_set(list(job.required_skills)) | canonical_set(list(job.tech_stack))
    from_body = False
    if not pool and job.description:
        sections = split_sections(job.description)
        pool = set(find_tech_in_text("\n".join(sections.required + sections.preferred + sections.duties)))
        from_body = bool(pool)
    mine = canonical_set(list(resume_skills))
    return SkillMatch(matched=tuple(sorted(pool & mine)), pool_size=len(pool), from_body=from_body)


@dataclass(frozen=True)
class PreferredMatch:
    """공고가 우대한다고 적은 것 중 이력서가 실제로 가진 것."""

    certifications: tuple[str, ...] = ()
    majors: tuple[str, ...] = ()

    @property
    def hit(self) -> bool:
        return bool(self.certifications or self.majors)


def preferred_match(job: Job, certifications: Sequence[str], majors: Sequence[str]) -> PreferredMatch:
    """우대 자격증·전공을 이력서와 맞대어 본다. 대조 규칙은 하드 필터와 같다.

    자격증은 양쪽을 정규화해 한쪽이 다른 쪽을 품으면 같은 것으로 본다
    (`정보처리기사` ↔ `정보처리기사 1급`). 전공은 갈래 용어가 이력서 전공 문자열에
    들어 있으면 맞은 것으로 본다 (`데이터` ⊂ `빅데이터과`).
    """
    mine = [normalize_term(c) for c in certifications if c.strip()]
    certs = tuple(
        cert for cert in job.preferred_certifications
        if (key := normalize_term(cert)) and any(key in c or c in key for c in mine)
    )
    my_majors = [normalize_term(m) for m in majors if m.strip()]
    hit_major = any(
        term and any(term in m for m in my_majors) for term in job.preferred_major_terms
    )
    return PreferredMatch(certs, tuple(job.preferred_majors) if hit_major else ())


def _normalized(values: list[float]) -> list[float]:
    """0~1로 편다. 전부 같으면 가운데(0.5)로 — 순서를 만들어내지 않는다."""
    low, high = min(values), max(values)
    if high <= low:
        return [0.5] * len(values)
    return [(v - low) / (high - low) for v in values]


T = TypeVar("T")


def pre_rank(
    candidates: Sequence[T],
    scores: Sequence[float],
    matches: Sequence[SkillMatch],
    preferred: Sequence[PreferredMatch] | None = None,
    *,
    weight: float = SKILL_WEIGHT,
    bonus: float = BONUS_WEIGHT,
) -> list[T]:
    """섞은 점수가 높은 순으로 다시 세운다. 같으면 들어온 순서를 지킨다.

    `scores`는 벡터 유사도(클수록 좋다), `matches`는 같은 자리의 기술 겹침이다.
    길이가 같아야 한다.

    `preferred`를 주면 우대 자격증·전공을 맞춘 공고에 `bonus`만큼 얹는다. **빼지는
    않는다.** 못 맞춘 공고와 우대 요건이 아예 없는 공고는 똑같이 0이다.
    """
    if len(candidates) != len(scores) or len(candidates) != len(matches):
        raise ValueError("후보·점수·겹침의 개수가 다릅니다")
    if preferred is not None and len(preferred) != len(candidates):
        raise ValueError("후보와 우대 대조의 개수가 다릅니다")
    if len(candidates) < 2:
        return list(candidates)

    known = [m.coverage for m in matches if m.coverage is not None]
    # 기술 정보가 없는 공고는 이 값을 받아 제자리에 남는다.
    neutral = sum(known) / len(known) if known else 0.0

    vectors = _normalized(list(scores))
    lifts = [bonus if p.hit else 0.0 for p in preferred] if preferred else [0.0] * len(candidates)
    blended = [
        (1 - weight) * v + weight * (m.coverage if m.coverage is not None else neutral) + lift
        for v, m, lift in zip(vectors, matches, lifts)
    ]
    order = sorted(range(len(candidates)), key=lambda i: (-blended[i], i))
    return [candidates[i] for i in order]
