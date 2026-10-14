"""AI 취업 코치 테스트.

테스트는 시계를 고정한다. 마감 판정·수집 시각이 `config.now()`를 따르므로, 고정하지
않으면 목업 공고(마감 2026-09-30)가 그날 이후로 전부 만료로 읽혀 결과가 날짜에 따라
달라진다. 이 패키지를 거쳐 도는 테스트는 모두 아래 시각을 "지금"으로 본다.
"""

import copy
from datetime import datetime
from typing import Any

from job_matching_bot.config import KST, freeze_now

AS_OF = datetime(2026, 9, 2, 12, 0, tzinfo=KST)
freeze_now(AS_OF)

# 사람인 상세 수집본 한 건의 모양. 크롤 결과가 없는 환경에서도 수집 경로를 태운다.
SARAMIN_SAMPLE: dict[str, Any] = {
    "source_job_id": "54845055",
    "source_url": "https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=54845055",
    "conditions": {
        "경력": "신입·경력",
        "학력": "대졸(4년제) 이상",
        "근무형태": "정규직 수습기간 3개월",
        "근무지역": "서울 마포구 지도보기",
    },
    "company_info": {"기업형태": "중소기업, 1000대기업, 주식회사"},
    "description": "Python과 FastAPI로 백엔드 API를 개발합니다.",
    "needs_human_review": False,
    "list_item": {
        "company": "주식회사 아이티에스코",
        "title": "솔루션 개발팀 신입•경력 채용",
        "job_sectors": ["백엔드/서버개발", "데이터엔지니어"],
        "support_text": "입사지원 D-6 7일 전 등록",
    },
}


def saramin_records(count: int) -> list[dict[str, Any]]:
    """ID만 다른 사람인 수집본 `count`건."""
    records = []
    for index in range(count):
        record = copy.deepcopy(SARAMIN_SAMPLE)
        job_id = str(int(SARAMIN_SAMPLE["source_job_id"]) + index)
        record["source_job_id"] = job_id
        record["source_url"] = f"https://www.saramin.co.kr/zf_user/jobs/view?rec_idx={job_id}"
        records.append(record)
    return records
