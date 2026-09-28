"""채용 사이트 공고 링크 → 수집한 공고의 job_id.

수집기는 사이트의 공고 번호로 job_id 를 만든다(`SARAMIN-{rec_idx}`, `JOBKOREA-{공고번호}`).
그래서 링크에서 번호만 꺼내면 jobs.jobs 를 기본 키로 바로 찾는다. source_url 로 LIKE 검색을 하지
않는다 — 같은 공고라도 주소에 붙는 추적 값(utm · Oem_Code 등)이 매번 달라서다.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

_JOBKOREA_PATH = re.compile(r"/recruit/gi_read/(\d+)", re.IGNORECASE)


def job_id_from_link(link: str) -> str | None:
    """사람인 · 잡코리아 공고 주소면 job_id, 아니면 None."""
    text = (link or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = f"https://{text}"
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    query = {key.lower(): values for key, values in parse_qs(parsed.query).items()}

    def number(*keys: str) -> str | None:
        for key in keys:
            for value in query.get(key, []):
                if value.isdigit():
                    return value
        return None

    if host == "saramin.co.kr" or host.endswith(".saramin.co.kr"):
        # PC 는 /zf_user/jobs/(relay/)view?rec_idx=N, 모바일은 /job-search/view?rec_idx=N
        rec_idx = number("rec_idx")
        return f"SARAMIN-{rec_idx}" if rec_idx else None
    if host == "jobkorea.co.kr" or host.endswith(".jobkorea.co.kr"):
        # 상세는 /Recruit/GI_Read/N, 본문 iframe 은 /Recruit/GI_Read_Comt_Ifrm?Gno=N
        found = _JOBKOREA_PATH.search(parsed.path)
        gno = found.group(1) if found else number("gno", "gi_no")
        return f"JOBKOREA-{gno}" if gno else None
    return None
