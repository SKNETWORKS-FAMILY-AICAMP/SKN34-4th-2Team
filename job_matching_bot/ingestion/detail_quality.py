"""상세 본문이 실제 텍스트인지 판정하는 공통 규칙.

과거 수집본에는 이미지가 한 장이라도 포함된 상세 페이지를 이미지 공고로 저장한
레코드가 있다. 본문에 업무·자격요건이 텍스트로 충분히 남아 있다면, 그 플래그는
첨삭과 매칭에서 신뢰하지 않는다.
"""

# 텍스트만 있는 공고 표본의 중앙값은 약 1,391자였다.
TEXT_BODY_MIN_CHARS = 800

# 짧아도 주요업무·자격요건이 실제 문장으로 남아 있으면 텍스트 공고다.
REQUIREMENT_MARKERS = (
    "자격요건", "지원자격", "주요업무", "담당업무", "우대사항", "모집분야", "모집부문",
)
REQUIREMENT_MIN_CHARS = 300


def has_requirement_text(body_text: str) -> bool:
    """요구역량을 본문 텍스트로 검증할 수 있는지 판정한다."""
    text = str(body_text or "").strip()
    if len(text) >= TEXT_BODY_MIN_CHARS:
        return True
    return len(text) >= REQUIREMENT_MIN_CHARS and any(
        marker in text for marker in REQUIREMENT_MARKERS
    )


def is_image_only_detail(body_text: str, stored_image_flag: object) -> bool:
    """저장 플래그와 실제 본문을 함께 보고 이미지 전용 공고만 True로 둔다."""
    if isinstance(stored_image_flag, str):
        flagged = stored_image_flag.strip().lower() in {"1", "true", "yes"}
    else:
        flagged = bool(stored_image_flag)
    return flagged and not has_requirement_text(body_text)
