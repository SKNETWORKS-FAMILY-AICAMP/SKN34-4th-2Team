"""바깥 데이터 — 국가자격 시험 일정(공공데이터포털)과 이번 주 커리큘럼 YouTube 추천.

둘 다 `system_cache` 에 받아 둔다. 원본은 Firebase Functions(`functions/src/qualExamSchd.ts`,
`functions/src/youtubeRecommendations.ts`)였다.

- 시험 일정: `qualExamSchedules_{연도}`. bootstrap 이 그대로 내려 준다. 하루에 한 번 새로 받는다.
- YouTube: `youtubeCurriculum_{기수 코드}_{주 시작일}_v3`. `/study/youtube-weekly` 가 읽는다.
  12시간이 지나면 다시 검색한다. 검색 한 번에 쿼터 100을 쓰므로(하루 1만) 요청마다 부르지 않는다.

키는 `.env` 의 `DATA_GO_KR_SERVICE_KEY`, `YOUTUBE_API_KEY`. 응답 본문에는 키가 실려 오므로 로그에 남기지 않는다.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from django.db import connection

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

QUAL_URL = "https://apis.data.go.kr/B490007/qualExamSchd/getQualExamSchdList"
QUAL_PAGE = 50
QUAL_STALE = timedelta(hours=24)
QUAL_DATE_FIELDS = (
    "docRegStartDt", "docRegEndDt", "docExamStartDt", "docExamEndDt", "docPassDt",
    "pracRegStartDt", "pracRegEndDt", "pracExamStartDt", "pracExamEndDt", "pracPassDt",
)

YT_URL = "https://www.googleapis.com/youtube/v3/search"
YT_TTL = timedelta(hours=12)
YT_VERSION = "v3"
YT_MAX_QUERIES = 5
YT_PER_QUERY = 6
YT_MAX_VIDEOS = 12

_qual_lock = threading.Lock()
_yt_locks: dict[str, threading.Lock] = {}
_yt_locks_guard = threading.Lock()


class FeedError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _env_key(name: str) -> str:
    key = (os.environ.get(name) or "").strip().strip('"').strip("'")
    # 포털은 인코딩 키와 디코딩 키를 둘 다 준다. 한 번 풀어 두고 보낼 때 한 번만 인코딩한다.
    return urllib.parse.unquote(key)


def _get_json(url: str, timeout: float = 20) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _cache_read(cur, key: str) -> tuple[dict | None, datetime | None]:
    cur.execute("SELECT data, synced_at FROM system_cache WHERE key = %s", [key])
    row = cur.fetchone()
    if not row:
        return None, None
    data = row[0]
    if isinstance(data, str):
        data = json.loads(data)
    return (data if isinstance(data, dict) else None), row[1]


def _cache_write(cur, key: str, data: dict) -> None:
    cur.execute(
        """INSERT INTO system_cache (key, data, synced_at) VALUES (%s, %s::jsonb, now())
           ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data, synced_at = EXCLUDED.synced_at""",
        [key, json.dumps(data, ensure_ascii=False)],
    )


# ── 국가자격 시험 일정 ─────────────────────────────────


def _qual_date(value) -> str | None:
    text = str(value or "").strip()
    if not text or text == "null":
        return None
    return text[:8]


def _qual_item(row: dict) -> dict:
    item = {
        "implYy": str(row.get("implYy") or ""),
        "implSeq": int(row.get("implSeq") or 0),
        "qualgbCd": str(row.get("qualgbCd") or ""),
        "qualgbNm": str(row.get("qualgbNm") or ""),
        "description": str(row.get("description") or ""),
    }
    for field in QUAL_DATE_FIELDS:
        item[field] = _qual_date(row.get(field))
    return item


def _qual_rows(payload: dict) -> list[dict]:
    body = payload.get("body") or (payload.get("response") or {}).get("body") or {}
    items = body.get("items") or body.get("item") or []
    if isinstance(items, dict):
        items = items.get("item") or []
    if isinstance(items, dict):
        items = [items]
    return [row for row in items if isinstance(row, dict)]


def fetch_qual_exams(year: int) -> tuple[list[dict], int]:
    key = _env_key("DATA_GO_KR_SERVICE_KEY")
    if not key:
        raise FeedError(503, "DATA_GO_KR_SERVICE_KEY가 설정되지 않았습니다.")
    items: list[dict] = []
    total = 0
    page = 1
    while True:
        query = urllib.parse.urlencode({
            "serviceKey": key, "numOfRows": QUAL_PAGE, "pageNo": page,
            "dataFormat": "json", "implYy": year, "qualgbCd": "T",
        })
        try:
            payload = _get_json(f"{QUAL_URL}?{query}")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise FeedError(502, f"시험 일정 API에 연결하지 못했습니다({type(exc).__name__}).") from None
        service_error = (payload.get("OpenAPI_ServiceResponse") or {}).get("cmmMsgHeader")
        if service_error:
            raise FeedError(502, str(service_error.get("returnAuthMsg") or service_error.get("errMsg") or "API 키 오류"))
        header = payload.get("header") or (payload.get("response") or {}).get("header") or {}
        if header.get("resultCode") not in (None, "00"):
            raise FeedError(502, str(header.get("resultMsg") or "시험 일정 API 오류"))
        rows = _qual_rows(payload)
        if page == 1:
            body = payload.get("body") or (payload.get("response") or {}).get("body") or {}
            total = int(body.get("totalCount") or len(rows))
        items.extend(_qual_item(row) for row in rows)
        if len(items) >= total or len(rows) < QUAL_PAGE:
            break
        page += 1
    items.sort(key=lambda i: i["docExamStartDt"] or i["docRegStartDt"] or i["pracExamStartDt"] or i["pracRegStartDt"] or "99991231")
    return items, total


def sync_qual_exams(years: list[int] | None = None) -> dict[int, int]:
    """시험 일정을 받아 `system_cache` 에 쓴다. 다음 해 일정은 나온 뒤(보통 12월)에만 저장한다."""
    this_year = datetime.now(KST).year
    targets = years or [this_year, this_year + 1]
    result: dict[int, int] = {}
    with _qual_lock:
        for year in targets:
            items, total = fetch_qual_exams(year)
            if not items and year != this_year:
                continue
            with connection.cursor() as cur:
                _cache_write(cur, f"qualExamSchedules_{year}", {
                    "year": year,
                    "items": items,
                    "totalCount": total,
                    "syncedAt": datetime.now(timezone.utc).isoformat(),
                })
            result[year] = len(items)
    return result


def qual_synced_at(year: int | None = None) -> datetime | None:
    year = year or datetime.now(KST).year
    with connection.cursor() as cur:
        cur.execute("SELECT synced_at FROM system_cache WHERE key = %s", [f"qualExamSchedules_{year}"])
        row = cur.fetchone()
    return row[0] if row else None


def sync_qual_exams_if_stale() -> dict[int, int] | None:
    """하루 넘게 묵었으면 새로 받는다. 키가 없으면 조용히 넘어간다."""
    if not _env_key("DATA_GO_KR_SERVICE_KEY"):
        return None
    synced = qual_synced_at()
    if synced is not None and datetime.now(timezone.utc) - synced < QUAL_STALE:
        return None
    return sync_qual_exams()


# ── 이번 주 커리큘럼 YouTube 추천 ──────────────────────

DATE_LABEL = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")


def _label_date(label: str) -> date | None:
    m = DATE_LABEL.search(label or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _unique(*values: str) -> list[str]:
    out: list[str] = []
    for raw in values:
        text = (raw or "").strip()
        if text and all(text.lower() != o.lower() for o in out):
            out.append(text)
    return out


def _join(*values: str) -> str:
    return re.sub(r"\s+", " ", " ".join(_unique(*values))).strip()


def _row_key(row: dict) -> str:
    return "|".join((row.get(k) or "").strip() for k in ("subject", "topic", "detail"))


def topic_label(row: dict) -> str:
    return (row.get("topic") or "").strip() or (row.get("subject") or "").strip() or "커리큘럼"


def _variants(row: dict) -> list[str]:
    """교과목 이름(「AI 활용 애플리케이션 개발」)은 너무 넓어 검색을 흐린다. 주제 · 세부 내용으로 찾는다."""
    subject, topic, detail = ((row.get(k) or "").strip() for k in ("subject", "topic", "detail"))
    core = _join(topic, detail) or subject
    out: list[str] = []
    for q in (f"{core} 강의", f"{core} 튜토리얼", f"{core} 개념 정리"):
        q = re.sub(r"\s+", " ", q).strip()
        if len(q) > 4 and q.lower() not in (o.lower() for o in out):
            out.append(q)
    return out


def pick_week_rows(rows: list[dict], today: date) -> tuple[date, list[dict]]:
    """이번 주(월~일) 커리큘럼 행. 이번 주가 비었으면 오늘과 가까운 날짜로 채운다."""
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    dated = [(r, d) for r in rows if (d := _label_date(r.get("date_label") or "")) is not None]
    by_distance = sorted(dated, key=lambda x: abs((x[1] - today).days))

    picked = [r for r, d in sorted(dated, key=lambda x: x[1]) if monday <= d <= sunday]
    if not picked and by_distance:
        nearest = by_distance[0][1]
        picked = [r for r, d in dated if nearest - timedelta(days=2) <= d <= nearest + timedelta(days=3)]

    # 이번 주 주제가 모자라면 가까운 날짜의 다른 주제로 채운다
    unique: list[dict] = []
    seen: set[str] = set()
    for r in picked + [r for r, _ in by_distance]:
        if len(unique) >= YT_MAX_QUERIES:
            break
        key = _row_key(r)
        if not key.replace("|", "").strip() or key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return monday, unique


def _search_queries(rows: list[dict]) -> list[tuple[str, str, str | None]]:
    per_row = [(topic_label(r), _variants(r)) for r in rows]
    queries: list[tuple[str, str, str | None]] = []
    seen: set[str] = set()

    def push(query: str, label: str, duration: str | None) -> None:
        if len(query) <= 2 or query.lower() in seen or len(queries) >= YT_MAX_QUERIES:
            return
        seen.add(query.lower())
        queries.append((query, label, duration))

    for label, variants in per_row:
        if variants:
            push(variants[0], label, "medium")
    for label, variants in per_row:
        if len(variants) > 1:
            push(variants[1], label, "long")
    for label, variants in per_row:
        for v in variants[2:]:
            push(v, label, "medium")
    return queries


def _search_youtube(key: str, query: str, duration: str | None) -> list[dict]:
    params = {
        "part": "snippet", "type": "video", "maxResults": YT_PER_QUERY, "q": query, "key": key,
        "relevanceLanguage": "ko", "regionCode": "KR", "safeSearch": "moderate",
    }
    if duration:
        params["videoDuration"] = duration
    try:
        payload = _get_json(f"{YT_URL}?{urllib.parse.urlencode(params)}")
    except urllib.error.HTTPError as exc:
        try:
            reason = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except (ValueError, OSError):
            reason = ""
        raise FeedError(502, f"YouTube 검색 실패({exc.code}) {reason}".strip()) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise FeedError(502, f"YouTube에 연결하지 못했습니다({type(exc).__name__}).") from None
    videos = []
    for item in payload.get("items") or []:
        video_id = (item.get("id") or {}).get("videoId")
        if not video_id:
            continue
        sn = item.get("snippet") or {}
        thumbs = sn.get("thumbnails") or {}
        thumb = next(
            (thumbs[k]["url"] for k in ("medium", "high", "default") if (thumbs.get(k) or {}).get("url")),
            f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        )
        videos.append({
            "videoId": video_id,
            "title": html.unescape(sn.get("title") or ""),
            "channelTitle": html.unescape(sn.get("channelTitle") or ""),
            "thumbnailUrl": thumb,
            "publishedAt": sn.get("publishedAt"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
    return videos


def _interleave(videos: list[dict], limit: int) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for v in videos:
        groups.setdefault(v["topicLabel"] or "_", []).append(v)
    out: list[dict] = []
    i = 0
    while len(out) < limit:
        added = False
        for group in groups.values():
            if i < len(group):
                out.append(group[i])
                added = True
                if len(out) >= limit:
                    break
        if not added:
            break
        i += 1
    return out


def _collect_videos(key: str, queries: list[tuple[str, str, str | None]]) -> list[dict]:
    collected: list[dict] = []
    seen_ids: set[str] = set()
    seen_channels: set[str] = set()
    errors: list[str] = []
    for query, label, duration in queries:
        try:
            found = _search_youtube(key, query, duration)
            if len(found) < 2:
                ids = {v["videoId"] for v in found}
                found += [v for v in _search_youtube(key, query, None) if v["videoId"] not in ids]
        except FeedError as exc:
            errors.append(exc.detail)
            continue
        fresh, rest = [], []
        for v in found:
            if v["videoId"] in seen_ids:
                continue
            seen_ids.add(v["videoId"])
            item = {**v, "topicLabel": label, "query": query}
            channel = v["channelTitle"].strip().lower()
            if channel and channel in seen_channels:
                rest.append(item)
            else:
                if channel:
                    seen_channels.add(channel)
                fresh.append(item)
        collected += fresh + rest
    if not collected and errors:
        raise FeedError(502, errors[0])
    return _interleave(collected, YT_MAX_VIDEOS)


def _cohort_for(cur, user: dict, cohort_code: str) -> dict:
    code = (cohort_code or user.get("cohort_code") or "").strip()
    if user.get("role") != "admin" and code != (user.get("cohort_code") or ""):
        raise FeedError(403, "자기 기수의 추천만 볼 수 있습니다.")
    cur.execute("SELECT id, code FROM cohorts WHERE code = %s", [code])
    row = cur.fetchone()
    if not row:
        raise FeedError(404, "기수를 찾을 수 없습니다.")
    return {"id": row[0], "code": row[1]}


def _curriculum_rows(cur, cohort_id: int) -> list[dict] | None:
    cur.execute(
        "SELECT id FROM curriculum_sheets WHERE cohort_id = %s ORDER BY uploaded_at DESC NULLS LAST, id DESC LIMIT 1",
        [cohort_id],
    )
    sheet = cur.fetchone()
    if not sheet:
        return None
    cur.execute(
        'SELECT date_label, subject, topic, detail FROM curriculum_rows WHERE sheet_id = %s ORDER BY "order", id',
        [sheet[0]],
    )
    return [dict(zip(("date_label", "subject", "topic", "detail"), r)) for r in cur.fetchall()]


def _yt_lock(key: str) -> threading.Lock:
    with _yt_locks_guard:
        return _yt_locks.setdefault(key, threading.Lock())


def weekly_youtube(user: dict, cohort_code: str = "", *, force: bool = False, today: date | None = None) -> dict:
    """이번 주 커리큘럼 주제로 찾은 YouTube 영상. 12시간 캐시. 검색이 실패하면 지난 캐시를 준다."""
    today = today or datetime.now(KST).date()
    if force and user.get("role") not in ("admin", "instructor"):
        force = False
    with connection.cursor() as cur:
        cohort = _cohort_for(cur, user, cohort_code)
        rows = _curriculum_rows(cur, cohort["id"])
    empty = {"cohortId": cohort["code"], "weekKey": None, "weekLabel": None, "topics": [], "videos": [],
             "cached": False, "fetchedAt": None}
    if rows is None:
        return {**empty, "message": "업로드된 커리큘럼이 없습니다."}
    monday, picked = pick_week_rows(rows, today)
    if not picked:
        return {**empty, "message": "커리큘럼에 날짜가 적힌 주제가 없습니다."}

    sunday = monday + timedelta(days=6)
    week_key = monday.strftime("%Y%m%d")
    week_label = f"{monday.month}/{monday.day} ~ {sunday.month}/{sunday.day}"
    topics = [topic_label(r) for r in picked]
    cache_key = f"youtubeCurriculum_{cohort['code']}_{week_key}_{YT_VERSION}"
    base = {"cohortId": cohort["code"], "weekKey": week_key, "weekLabel": week_label, "topics": topics}

    def from_cache(data: dict, synced: datetime | None, message: str | None = None) -> dict:
        return {**base, "topics": data.get("topics") or topics, "videos": data.get("videos") or [],
                "cached": True, "fetchedAt": synced.isoformat() if synced else None, "message": message}

    with connection.cursor() as cur:
        cached, synced = _cache_read(cur, cache_key)
    fresh = cached is not None and synced is not None and datetime.now(timezone.utc) - synced < YT_TTL
    if fresh and not force:
        return from_cache(cached, synced)

    key = _env_key("YOUTUBE_API_KEY")
    if not key:
        if cached:
            return from_cache(cached, synced)
        return {**base, "videos": [], "cached": False, "fetchedAt": None,
                "message": "YOUTUBE_API_KEY가 설정되지 않아 추천을 만들 수 없습니다."}

    # 같은 주를 여러 명이 동시에 열어도 검색은 한 번만
    with _yt_lock(cache_key):
        with connection.cursor() as cur:
            cached, synced = _cache_read(cur, cache_key)
        if not force and cached is not None and synced is not None and datetime.now(timezone.utc) - synced < YT_TTL:
            return from_cache(cached, synced)
        try:
            videos = _collect_videos(key, _search_queries(picked))
        except FeedError as exc:
            logger.warning("youtube weekly failed: %s", exc.detail)
            if cached:
                return from_cache(cached, synced, "새 영상을 가져오지 못해 지난 추천을 보여 줍니다.")
            return {**base, "videos": [], "cached": False, "fetchedAt": None,
                    "message": "YouTube 추천을 가져오지 못했습니다. 잠시 뒤 다시 시도해 주세요."}
        with connection.cursor() as cur:
            _cache_write(cur, cache_key, {"weekKey": week_key, "weekLabel": week_label, "topics": topics,
                                          "queries": [q for q, _, _ in _search_queries(picked)], "videos": videos})
    return {**base, "videos": videos, "cached": False,
            "fetchedAt": datetime.now(timezone.utc).isoformat(), "message": None if videos else "찾은 영상이 없습니다."}
