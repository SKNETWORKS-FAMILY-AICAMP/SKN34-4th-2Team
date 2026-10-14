"""통제된 Mock 공고 소스.

실수집 데이터만으로는 Hard Filter의 PASS/CHECK_REQUIRED/FAIL 세 갈래와
명시적 기술요건 매칭을 모두 재현할 수 없어, 조건을 통제한 공고를 함께 넣는다.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from job_matching_bot.config import now
from job_matching_bot.schemas.job_posting import Job

PARSER_VERSION = "mock-0.1.0"

MOCK_FIXTURES: list[dict[str, Any]] = [
    {
        "source_job_id": "MOCK-BE-001",
        "company": "테스트 데이터랩",
        "title": "주니어 백엔드·AI 서비스 개발자",
        "description": "FastAPI REST API와 PostgreSQL 기반 추천 서비스를 개발하고 Docker로 배포합니다.",
        "required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        "preferred_skills": ["AWS", "Kubernetes", "Redis"],
        "career_type": "ENTRY",
        "min_career_years": 0,
        "education": "학력무관",
        "region": "서울 성동구",
        "employment_type": "정규직",
    },
    {
        "source_job_id": "MOCK-FE-002",
        "company": "테스트 프론트",
        "title": "React 프론트엔드 개발자",
        "description": "React와 TypeScript로 사용자 화면을 개발합니다.",
        "required_skills": ["React", "TypeScript"],
        "preferred_skills": ["Figma"],
        "career_type": "ENTRY",
        "min_career_years": 0,
        "education": "학력무관",
        "region": "서울 마포구",
        # 고용형태 미기재 → Hard Filter의 CHECK_REQUIRED 경로를 재현한다.
        "employment_type": "미기재",
    },
    {
        "source_job_id": "MOCK-BE-003",
        "company": "테스트 시니어랩",
        "title": "시니어 Python 백엔드 개발자",
        "description": "Python API 서버와 클라우드 인프라를 운영합니다.",
        "required_skills": ["Python", "AWS"],
        "preferred_skills": ["Docker"],
        # 신입 이력서로는 통과할 수 없는 조건 → FAIL 경로를 재현한다.
        "career_type": "EXPERIENCED",
        "min_career_years": 5,
        "education": "학력무관",
        "region": "부산 해운대구",
        "employment_type": "정규직",
    },
]


def mock_jobs(as_of: datetime | None = None) -> list[Job]:
    as_of = as_of or now()
    jobs = []
    for value in MOCK_FIXTURES:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
        jobs.append(
            Job(
                job_id=value["source_job_id"],
                source="MOCK",
                source_job_id=value["source_job_id"],
                source_url=f"mock://{value['source_job_id']}",
                company=value["company"],
                company_type="테스트기업",
                title=value["title"],
                description=value["description"],
                required_skills=value["required_skills"],
                preferred_skills=value["preferred_skills"],
                career_type=value["career_type"],
                min_career_years=value["min_career_years"],
                education=value["education"],
                region=value["region"],
                employment_type=value["employment_type"],
                posted_at=as_of.date().isoformat(),
                deadline="2026-09-30T23:59:59+09:00",
                status="OPEN",
                content_hash=f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}",
                parser_version=PARSER_VERSION,
                field_provenance={
                    "required_skills": {
                        "method": "test_fixture",
                        "evidence": value["required_skills"],
                        "confidence": 1.0,
                    },
                    "preferred_skills": {
                        "method": "test_fixture",
                        "evidence": value["preferred_skills"],
                        "confidence": 1.0,
                    },
                },
            )
        )
    return jobs
