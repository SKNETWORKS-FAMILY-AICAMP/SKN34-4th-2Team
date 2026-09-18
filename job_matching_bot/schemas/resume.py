"""매칭 엔진이 사용하는 개인정보 비포함 Resume Profile 스키마.

`mock_resumes()`는 Hard Filter와 Ranking의 서로 다른 갈래를 밟도록 만든 가상
인물들이다. 실제 사람의 정보가 아니며, 각 인물이 어느 갈래를 검증하는지
주석에 적어 둔다. 인물을 추가할 때는 "기존 인물이 못 밟는 갈래"가 무엇인지
먼저 적는다.
"""

from dataclasses import dataclass, field


@dataclass
class ResumeProfile:
    resume_id: str
    target_roles: list[str]
    skills: list[str]
    project_skills: list[str]
    preferred_regions: list[str]
    preferred_employment_types: list[str]
    education_level: str
    career_years: int
    confirmed_missing_skills: list[str] = field(default_factory=list)
    # 이력서 학력사항의 전공과 자격사항 이름. 전공·자격증 요건 판정에 쓴다.
    majors: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)


def sample_resume() -> ResumeProfile:
    """외부 API나 개인정보 없이 재현 가능한 Phase 1 테스트 이력서."""
    return mock_resumes()["backend_entry"]


def mock_resumes() -> dict[str, ResumeProfile]:
    """검증용 가상 이력서. 키는 안정적인 식별자라 테스트와 CLI가 그대로 쓴다."""
    return {
        # 기준 인물. 파이프라인 자체 검증(validation.py)이 이 인물로 1순위를 확인한다.
        "backend_entry": ResumeProfile(
            resume_id="resume-test-001",
            target_roles=["백엔드 개발자", "AI 엔지니어"],
            skills=["Python", "Django", "FastAPI", "PostgreSQL", "Docker", "AWS"],
            project_skills=["Python", "FastAPI", "PostgreSQL", "pgvector"],
            preferred_regions=["서울"],
            preferred_employment_types=["정규직", "계약직"],
            education_level="대졸",
            career_years=0,
            # 테스트 사용자가 실사용 경험이 없다고 명시적으로 확인한 fixture다.
            confirmed_missing_skills=["Kubernetes"],
        ),
        # 프론트엔드 신입. 백엔드 공고가 위로 올라오면 직무 점수가 잘못된 것이다.
        # 표기 변형(React Native, Next.js)이 태그와 맞는지도 이 인물로 본다.
        "frontend_entry": ResumeProfile(
            resume_id="resume-test-002",
            target_roles=["프론트엔드 개발자"],
            skills=["JavaScript", "TypeScript", "React", "React Native", "Next.js", "CSS"],
            project_skills=["React", "TypeScript"],
            preferred_regions=["서울", "경기"],
            preferred_employment_types=["정규직"],
            education_level="대졸",
            career_years=0,
        ),
        # 백엔드 경력 3년. "경력 5~15년" 공고는 FAIL, "경력 3년 ↑"는 PASS여야 한다.
        # 이력서 표기 "Spring Boot"가 태그 "SpringBoot"와 맞아야 한다.
        "backend_experienced_3y": ResumeProfile(
            resume_id="resume-test-003",
            target_roles=["백엔드 개발자"],
            skills=["Java", "Spring Boot", "JPA", "MySQL", "Redis", "AWS", "Docker", "Git"],
            project_skills=["Java", "Spring Boot", "MySQL", "AWS"],
            preferred_regions=["서울"],
            preferred_employment_types=["정규직"],
            education_level="대졸",
            career_years=3,
        ),
        # 데이터 직무, 초대졸. "대졸(4년제) 이상"은 FAIL, "대졸(2,3년제) 이상"은 PASS.
        # 학력 랭크에 초대졸을 넣은 이유가 이 인물이다.
        "data_entry_junior_college": ResumeProfile(
            resume_id="resume-test-004",
            target_roles=["데이터 엔지니어"],
            skills=["Python", "SQL", "Pandas", "Spark", "Airflow", "Tensorflow"],
            project_skills=["Python", "SQL", "Pandas"],
            preferred_regions=["경기", "서울"],
            preferred_employment_types=["정규직", "계약직"],
            education_level="초대졸",
            career_years=0,
        ),
        # 임베디드 신입, 수도권 밖. 대전 공고는 지역 PASS, 서울 공고는 FAIL이어야 한다.
        # 한글 태그(임베디드리눅스)와 C/C++ 구분이 이 인물로 검증된다.
        "embedded_entry_regional": ResumeProfile(
            resume_id="resume-test-005",
            target_roles=["임베디드 개발자"],
            skills=["C", "C++", "Linux", "임베디드 리눅스", "RTOS", "Git"],
            project_skills=["C", "Linux"],
            preferred_regions=["대전", "충청"],
            preferred_employment_types=["정규직"],
            education_level="대졸",
            career_years=0,
        ),
    }
