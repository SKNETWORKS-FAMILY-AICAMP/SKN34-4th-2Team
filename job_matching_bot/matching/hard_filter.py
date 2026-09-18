"""명시 조건 기반 Hard Filter.

확인할 수 없는 조건은 탈락으로 단정하지 않고 `CHECK_REQUIRED`로 남긴다.
공고에 적혀 있지 않은 것과 지원자가 충족하지 못한 것은 다르다.
"""

from __future__ import annotations

import re
from typing import Any

from job_matching_bot.schemas.job_posting import Job
from job_matching_bot.schemas.resume import ResumeProfile

# 초대졸(전문대 2,3년제)은 고졸과 대졸 사이다. 이 표는
# functions/src/jobCoachScoring.ts 의 EDUCATION_RANK 와 같아야 한다.
# 신입 전용 공고를 걸러낼 연차 경계. 이 값 이상이면 신입 전형 대상이 아니다.
ENTRY_ONLY_MAX_YEARS = 2

EDUCATION_RANK = {"학력무관": 0, "고졸": 1, "초대졸": 2, "대졸": 3, "석사": 4, "박사": 5}


def _education_passes(resume_level: str, required_level: str) -> bool | None:
    """학력 충족 여부. 판단할 수 없으면 `None`을 돌려준다."""
    if required_level in ("학력무관", "미기재"):
        return True if required_level == "학력무관" else None
    if resume_level not in EDUCATION_RANK or required_level not in EDUCATION_RANK:
        return None
    return EDUCATION_RANK[resume_level] >= EDUCATION_RANK[required_level]


NATIONWIDE = "전국"


def is_nationwide(job_region: str) -> bool:
    """공고 지역이 '전국'을 포함하면 어느 희망 지역이든 통과시킨다.

    local_job_matcher.dart / jobCoach.ts 의 같은 규칙과 맞춰야 한다.
    """
    return NATIONWIDE in job_region


def normalize_term(text: str) -> str:
    """공백·기호를 지우고 소문자로. qualifications.py 및 다른 매처와 같은 정규화."""
    return re.sub(r"[\s\-_/·.()\[\]]", "", text).lower()


def _qualification_checks(
    job: Job, resume: ResumeProfile,
    passed: list[str], unknown: list[str], failed: list[str],
) -> None:
    """전공·자격증·병역.

    **자격증만 탈락시킨다.** 자격요건에 적힌 필수 자격증이 없으면 지원해도 안 된다.
    전공·병역은 확인 필요로 둔다 — 학과 이름이 제각각이고 병역은 이력서로 확인할
    성격이 아니라, 잘라내면 억울한 탈락이 많다.

    탈락으로 바꾸기 전에 추출을 먼저 손봤다. `홍보기사`·`운전기사`처럼 자격증이 아닌
    말, `~ 등 IT 관련 자격증` 같은 예시 문장, 같은 자격증이 두 묶음에 든 경우를
    걸러내 363건이 320건이 됐다. 그 상태가 아니면 자격 있는 사람이 탈락한다.
    """
    if job.required_majors:
        resume_majors = [m.strip() for m in resume.majors if m.strip()]
        if not resume_majors:
            unknown.append(f"전공 확인 필요: {', '.join(job.required_majors)}")
        else:
            matched = [
                m for m in resume_majors
                if any(term and term in normalize_term(m) for term in job.required_major_terms)
            ]
            if matched:
                passed.append(f"전공 요건 충족: {matched[0]}")
            else:
                unknown.append(
                    f"전공 요건 미확인: 공고 {', '.join(job.required_majors)} / 이력서 {', '.join(resume_majors)}"
                )
    resume_certs = [normalize_term(c) for c in resume.certifications if c.strip()]

    def _holds(cert: str) -> bool:
        key = normalize_term(cert)
        return bool(key) and any(key in c or c in key for c in resume_certs)

    # 한 묶음은 "이 중 하나"다. `대기환경기사 또는 산업위생관리기사`처럼 대안을 나열한
    # 공고가 자격증이 잡힌 669건 중 과반이다. 하나씩 따로 검사하면 자격을 갖춘 사람이
    # 나머지를 안 가졌다는 이유로 걸린다.
    #
    # 묶음이 없는 옛 저장소 행은 평평한 목록을 각각 한 묶음으로 본다. 예전과 같다.
    groups = job.required_certification_groups or [[c] for c in job.required_certifications]
    for group in groups:
        names = ", ".join(group)
        if any(_holds(cert) for cert in group):
            passed.append(f"자격증 요건 충족: {names}")
        else:
            failed.append(f"필수 자격증 {names}")
    if job.military_required:
        unknown.append("병역 조건 확인 필요 (병역필 또는 면제)")


def hard_filter(job: Job, resume: ResumeProfile) -> dict[str, Any]:
    failed: list[str] = []
    unknown: list[str] = []
    passed: list[str] = []

    if job.status != "OPEN":
        failed.append(f"공고 상태 {job.status}")
    else:
        passed.append("공고 진행 중")

    # 본문이 이미지뿐이면 텍스트로 확인한 요구사항이 없다. 탈락이 아니라 확인 필요다.
    if job.body_is_image:
        unknown.append("공고 상세가 이미지라 요구사항 미확인")

    if job.career_type == "EXPERIENCED":
        if job.min_career_years is None:
            # "경력자"라고만 쓰고 연차가 없는 공고. 경력이 있으면 충족이다.
            #
            # 신입에게는 **탈락**이다. 미기재인 것은 연차이지 "경력자를 뽑는다"는 사실이
            # 아니다. 몇 년인지 모르는 것과 경력자용인지 모르는 것은 다르다. 확인 필요로
            # 두었더니 신입 이력서에 경력 공고가 적합도 "높음"으로 나갔다(25건 중 6건).
            if resume.career_years >= 1:
                passed.append("경력 조건 충족 (연차 미기재, 경력 보유)")
            else:
                failed.append("경력자 채용 (연차 미기재)")
        elif resume.career_years < job.min_career_years:
            failed.append(f"최소 경력 {job.min_career_years}년")
        else:
            passed.append("경력 조건 충족")
    elif job.career_type == "ENTRY" and resume.career_years >= ENTRY_ONLY_MAX_YEARS:
        # 신입만 뽑는다고 적은 공고다. 경력자에게는 맞지 않는다.
        #
        # 예전에는 ENTRY도 무조건 통과였다. 연차 조건을 "이 사람이 모자라지 않은가"로만
        # 봤기 때문이다. 방향이 반대인 경우를 안 봤다. 사람이 매긴 43건에서 경력 3년
        # 이력서에 "백엔드 개발자 (신입)" 공고가 올라왔고 사람이 걸렀다.
        #
        # 경계는 2년으로 둔다. 신입 공고는 사실상 0~1년차를 받는다. 2년차부터는
        # 신입 전형에 넣을 자리가 아니다. 표본에 경력 이력서가 하나뿐이라 이 숫자는
        # 관례에서 가져온 것이지 측정한 값이 아니다.
        failed.append("신입 채용 (경력자 대상 아님)")
    elif job.career_type in ("ENTRY", "ANY"):
        passed.append("경력 조건 충족")
    else:
        unknown.append("경력 조건 미기재")

    education_result = _education_passes(resume.education_level, job.education)
    if education_result is True:
        passed.append("학력 조건 충족")
    elif education_result is False:
        failed.append(f"필수 학력 {job.education}")
    else:
        unknown.append("학력 조건 미기재")

    _qualification_checks(job, resume, passed, unknown, failed)

    # 희망 지역을 안 골랐으면 지역은 따지지 않는다. 빈 목록을 그대로 아래로 흘리면
    # "어느 지역에도 안 맞는다"가 되어 거의 모든 공고가 탈락한다.
    if not resume.preferred_regions:
        passed.append("희망 지역 제한 없음")
    elif job.region == "미기재":
        unknown.append("근무지역 미기재")
    elif is_nationwide(job.region) or NATIONWIDE in resume.preferred_regions:
        # 공고가 전국 근무이거나 사용자가 전국을 골랐으면 지역은 따지지 않는다.
        passed.append("전국 근무 가능 — 지역 조건 충족")
    elif any(region in job.region for region in resume.preferred_regions):
        passed.append("희망 근무지역 일치")
    else:
        failed.append(f"희망지역 불일치: {job.region}")

    if not resume.preferred_employment_types:
        passed.append("고용형태 제한 없음")
    elif job.employment_type == "미기재":
        unknown.append("고용형태 미기재")
    elif job.employment_type in resume.preferred_employment_types:
        passed.append("희망 고용형태 일치")
    else:
        failed.append(f"희망 고용형태 불일치: {job.employment_type}")

    status = "FAIL" if failed else "CHECK_REQUIRED" if unknown else "PASS"
    return {"status": status, "passed": passed, "failed": failed, "unknown": unknown}
