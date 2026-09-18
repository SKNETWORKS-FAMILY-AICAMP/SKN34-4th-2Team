"""매칭 엔진: 명시 조건 Hard Filter.

이 레이어는 이미 정규화된 `Job`만 받는다. 수집·정규화는 `ingestion`의 책임이다.
순위는 추천 서버(`api/`)의 벡터 검색과 LLM 재정렬이 정한다.
"""

from job_matching_bot.matching.hard_filter import hard_filter

__all__ = ["hard_filter"]
