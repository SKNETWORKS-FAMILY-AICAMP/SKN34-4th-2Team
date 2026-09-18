"""추천 서비스(`RecommendService`)와 공고 찾기 챗봇(`ChatService`).

추천은 일곱 단계를 순서대로 실행한다.

    ① LLM 구조화   이력서 → 검색 질의문 (앱이 미리 보낸 profile이 있으면 건너뜀)
    ② 벡터 검색     Pinecone Top-25 (조건 필터 동시 적용)
    ③ 하드 필터     경력·학력·희망 조건으로 후보 좁히기
    ④ 마감 확인     마감 시각이 지났거나 사이트에서 조기 마감된 공고 빼기
    ⑤ 사전 순위     벡터 순위 + 기술 겹침으로 LLM에 보낼 12건 고르기
    ⑥ LLM 재정렬    12건 병렬로 적합도와 근거 문장
    ⑦ 근거 검증     원문에 없는 인용 제거, 회사당 상한 적용

실패했을 때의 방침이 단계마다 다르다.

- ①·④·⑥ 실패 → 이어서 진행한다. ①은 이력서 원문으로 검색하고, ④는 전부 열려 있다고
  보며, ⑥은 ⑤의 순서를 쓰고 판정 못 받은 공고를 "낮음"으로 둔다. 결과 품질이 떨어질 뿐
  엉뚱한 공고가 나오지는 않는다.
- ②·③ 실패 → **추천하지 않는다.** 검색이 안 되면 근거가 없고, 하드 필터가 안 돌면
  조건 위반 공고가 나간다. 아무거나 보여 주는 것보다 실패를 알리는 편이 낫다.

챗봇은 `ChatService`의 설명과 `docs/chatbot.md`에 있다.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from job_matching_bot.api import abuse, prompts, schemas
from job_matching_bot.matching.hard_filter import hard_filter
from job_matching_bot.matching.pre_ranker import pre_rank, preferred_match, skill_match
from job_matching_bot.retrieval import search as retrieval
from job_matching_bot.retrieval import market_stats, store_search
from job_matching_bot.schemas.job_posting import Job
from job_matching_bot.schemas.resume import ResumeProfile

# 검색으로 가져올 후보 수. 하드 필터에서 일부가 떨어지므로 최종 표시분보다 넉넉히.
SEARCH_TOP_K = 25
# LLM에 넘길 상위 후보 수. 공고마다 따로, 동시에 판정하므로 늘려도 가장 느린 한 건만큼만
# 기다린다. 6건에서 12건으로 올렸을 때 실측(이력서 4종): 시간은 6.6초에서 7.0초로 0.4초
# 늘고, "높음" 판정은 9건에서 18건으로 늘었다. 벡터 검색이 위로 올린 순서가 사람이 보기에
# 늘 맞지는 않아, 적게 보면 좋은 공고를 판정도 못 해 보고 버리게 된다.
# 하드 필터를 통과하는 것이 보통 13~18건이라 12건은 그 안에 든다.
RERANK_TOP_K = 12
# 같은 회사가 목록을 채우지 않게 하는 상한.
MAX_PER_COMPANY = 2

# 적합도 순서. 판정을 못 받은 공고(None)는 판정된 '낮음' 뒤에 선다.
_FIT_ORDER = {"높음": 0, "보통": 1, "낮음": 2}
UNJUDGED_CONCERN = "AI 세부 분석을 완료하지 못했습니다. 검색 순서로만 배치했습니다."


def fit_order(fit: str | None) -> int:
    """정렬 키. 값이 없거나 모르는 값이면 맨 뒤."""
    return _FIT_ORDER.get(fit or "", len(_FIT_ORDER))
# 재정렬에 넘길 공고 본문 길이. 메타데이터 excerpt와 같게 두어 자르지 않는다.
JOB_EXCERPT_CHARS = 1200
# LLM 추론 강도. 대조 작업이라 낮춰도 근거 품질이 유지되고 응답이 크게 빨라진다.
REASONING_EFFORT = "medium"
# 챗봇이 말을 가르는 호출만 따로 낮춘다.
#
# 위 medium은 **추천 재정렬**을 재서 정한 값이다(`_build_generator` 설명의 표). 거기서는
# low가 맞는 공고를 놓쳤다. 가르기는 그 값을 물려받았을 뿐 따로 재 본 적이 없었다.
#
# 재 봤다. 검색·질문·추천·잡담·범위밖·번호 가리키기·비교·급여까지 13가지를 넣고
# 강도만 바꿨다.
#
#     low     13/13  평균 1.7초   (네 번 돌려 전부 13/13)
#     medium  13/13  평균 3.0초
#
# 가르는 일은 깊이 생각할 것이 없다. 모든 말이 이 호출을 지나므로 여기서 줄면 전부
# 줄어든다. 답을 쓰는 호출은 medium 그대로다 — 그건 글의 질이 걸린 일이다.
# minimal은 이 모델이 받지 않는다.
CHAT_EFFORT = "low"
# 구조화 결과를 몇 벌까지 들고 있을지. 이력서 한 건이 몇 KB라 넉넉해도 가볍다.
PROFILE_CACHE_SIZE = 64


# 추천이 거치는 단계. 앱이 이 순서대로 줄을 세운다. 이름을 바꾸면 앱도 같이 고쳐야 한다.
RECOMMEND_STAGES = ("resume", "search", "filter", "judge")


# 잡담에 돌려줄 말은 모델이 쓴다. 이것은 모델이 아무 말도 안 돌려줬을 때의 자리다.
# 빈 말풍선을 띄우느니 무엇을 물으면 되는지라도 보여 준다.
SMALL_TALK_FALLBACK = (
    "채용에 대한 것을 도와드릴 수 있어요.\n"
    "공고를 찾으시려면 “서울 백엔드 신입”처럼, "
    "궁금한 게 있으시면 “백엔드 신입은 뭘 준비해야 해?”처럼 물어보세요."
)


# 채용 밖의 일을 시켰을 때. **이 말은 모델이 쓰지 않는다.**
#
# 프롬프트로 "채용 이야기만 하라"고 이르는 것과, 답을 쓰는 단계로 아예 안 보내는 것은
# 다르다. 앞은 모델이 매번 지켜 줘야 하지만 뒤는 지킬 일이 없다. 실제로 "호구"라는
# 말 하나에 뜻풀이와 "이 말을 부드럽게 바꿔 말해줘" 같은 제안까지 붙어 나갔다.
OFF_TOPIC_REPLY = (
    "저는 채용과 취업 준비에 대해서만 도와드릴 수 있어요.\n"
    "공고를 찾거나, 무엇을 준비하면 좋을지 물어봐 주세요."
)


def _progress_reporter(
    progress: Callable[[str, str | None], None] | None,
) -> Callable[..., None]:
    """진행 알림을 부르되 실패는 삼킨다.

    알림은 곁다리다. 듣는 쪽이 끊겼다고 추천까지 실패하면 본말이 뒤집힌다.
    """
    if progress is None:
        return lambda *_args: None

    def say(stage: str, detail: str | None = None) -> None:
        try:
            progress(stage, detail)
        except Exception:  # noqa: BLE001 — 알림 실패가 추천을 막을 이유는 없다
            pass

    return say


class StageClock:
    """단계마다 걸린 시간을 잰다.

    요청 전체 시간만 로그에 남아서 "추천이 10초대"라는 말이 어느 단계 탓인지 가릴 수
    없었다. `lap(이름)`은 직전 `lap`부터 지금까지를 그 이름으로 적는다.
    """

    def __init__(self, now: Callable[[], float] = time.perf_counter) -> None:
        self._now = now
        self._started = self._last = now()
        self.laps: dict[str, int] = {}

    def lap(self, name: str) -> None:
        current = self._now()
        self.laps[name] = self.laps.get(name, 0) + round((current - self._last) * 1000)
        self._last = current

    def timings(self) -> dict[str, int]:
        return {**self.laps, "total": round((self._now() - self._started) * 1000)}


# 로그에 찍을 단계 이름. 응답의 `timings_ms` 열쇠와 같다.
STAGE_LABELS = {
    "profile": "구조화",
    "search": "검색",
    "filter": "필터",
    "liveness": "마감 확인",
    "pre_rank": "사전 순위",
    "rerank": "재정렬",
    "verify": "근거 검증",
    "total": "합계",
}


def format_timings(timings: dict[str, int], profile_source: str) -> str:
    parts = [f"{STAGE_LABELS.get(k, k)} {v / 1000:.1f}" for k, v in timings.items()]
    return f"[추천 시간] 구조화 출처={profile_source} · " + " · ".join(parts) + "초"


# 챗봇 단계 이름. 갈래마다 지나는 단계가 달라 응답에는 지난 것만 실린다.
CHAT_STAGE_LABELS = {
    "route": "가르기",
    "store": "공고 읽기",
    "search": "조건 조회",
    "meaning": "뜻으로 찾기",
    "stats": "집계",
    "liveness": "마감 확인",
    "answer": "답 쓰기",
    "total": "합계",
}


def format_chat_timings(timings: dict[str, int], mode: str) -> str:
    parts = [f"{CHAT_STAGE_LABELS.get(k, k)} {v / 1000:.1f}" for k, v in timings.items()]
    return f"[챗봇 시간] {mode} · " + " · ".join(parts) + "초"


class StoreUnavailable(RuntimeError):
    """공고 저장소 파일이 없다. 팀원은 공유 파일을 받아야 한다."""


class SearchUnavailable(RuntimeError):
    """벡터 검색이나 하드 필터가 실패했다. 추천을 내보내지 않는다."""



def _build_generator(prompt, schema, effort: str | None = None):
    """프롬프트 | 구조화 출력. 첨삭 모듈과 같은 방식으로 맞춘다.

    추론 강도는 medium이다. 한때 low로 두었는데, 대조하는 일이니 깊게 생각해도 나아지지
    않으리라 본 것이었다. 이력서 하나로만 재고 내린 판단이었고, 다른 이력서로 재보니
    틀렸다. **low는 맞는 공고를 놓친다.**

    후보 12건 재정렬 실측:

        이력서        low                medium             high
        AI/데이터     8.8초 높음5 탈락1    15.3초 높음5 탈락0   58.2초 높음6 탈락3
        백엔드        8.0초 높음3 탈락3    10.8초 높음2 탈락0   31.9초 높음2 탈락0
        앱 개발       8.3초 높음1 탈락1    10.6초 높음5 탈락1   19.8초 높음4 탈락0

    앱 개발 이력서에서 low는 Flutter 공고를 1건만 "높음"으로 봤고 medium은 5건을 찾았다.
    "탈락"은 원문에 없어 검증 단계에서 지운 인용 수다 — low가 가장 많이 지어냈다.
    high는 medium보다 나은 것이 없으면서 두세 배 느리다.

    `OPENAI_REASONING_EFFORT`로 바꿀 수 있다.
    """
    import os

    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
        reasoning_effort=effort
        or os.environ.get("OPENAI_REASONING_EFFORT", REASONING_EFFORT),
        max_retries=2,
    )
    return (prompt | model.with_structured_output(schema, method="json_schema")).invoke


class _LivenessMixin:
    """내려간 공고를 내보내기 직전에 걸러 내는 손잡이.

    저장소 상태는 밤에 한 번 맞춘 것이라 낮에 조기 마감된 공고를 모른다. 마감일이
    미래고 어젯밤 목록에도 있었는데 오늘 사이트에서는 "접수마감"인 공고가 실제로 있다.
    그건 페이지를 열어 봐야만 안다. 그래서 **사용자에게 나갈 것만** 그 자리에서 본다.

    확인이 안 되면(네트워크 오류·차단) 그대로 내보낸다. 잘못 지우는 것보다 낫다.
    """

    _liveness = None

    @property
    def liveness(self):
        if self._liveness is None:
            from job_matching_bot.retrieval.liveness import Liveness

            self._liveness = Liveness(self.store_path)
        return self._liveness

    def drop_dead(self, job_ids: list[str]) -> set[str]:
        """살아 있는 job_id 집합. 확인이 실패하면 전부 살아 있는 것으로 본다."""
        try:
            return set(self.liveness.alive(job_ids))
        except Exception:  # noqa: BLE001 — 확인 실패가 추천을 막을 이유는 아니다
            return set(job_ids)


class RecommendService(_LivenessMixin):
    def __init__(self, profiler=None, reranker=None, store_path: Path | None = None) -> None:
        self._profiler = profiler
        self._reranker = reranker
        self._store_path = store_path
        # 같은 이력서로 다시 추천하면 구조화를 건너뛴다. 앱은 범위(프로젝트·기술스택 …)를
        # 바꿔 가며 여러 번 부르는데, 범위마다 글이 다르므로 글 자체를 열쇠로 쓴다.
        self._profiles: OrderedDict[str, schemas.ResumeProfileOut] = OrderedDict()

    @property
    def store_path(self) -> Path:
        if self._store_path is None:
            from job_matching_bot.ingest import DEFAULT_STORE

            self._store_path = DEFAULT_STORE
        return self._store_path

    @property
    def profiler(self):
        if self._profiler is None:
            self._profiler = _build_generator(prompts.PROFILE_PROMPT, schemas.ResumeProfileOut)
        return self._profiler

    @property
    def reranker(self):
        if self._reranker is None:
            self._reranker = _build_generator(prompts.RERANK_PROMPT, schemas.RerankOut)
        return self._reranker

    # ── ① 이력서 구조화 ──────────────────────────────
    def build_profile(
        self, request: schemas.RecommendRequest, warnings: list[str]
    ) -> schemas.ResumeProfileOut:
        # 앱이 저장할 때 미리 만들어 보냈으면 그대로 쓴다. 다시 만들면 검색어가 달라져
        # 같은 이력서인데도 추천이 흔들린다.
        if request.profile is not None:
            return request.profile
        cached = self._profiles.get(request.resume_text)
        if cached is not None:
            self._profiles.move_to_end(request.resume_text)
            return cached
        try:
            profile = self.profiler({"resume_text": request.resume_text})
            self._profiles[request.resume_text] = profile
            if len(self._profiles) > PROFILE_CACHE_SIZE:
                self._profiles.popitem(last=False)
            return profile
        except Exception as error:
            warnings.append(f"이력서 구조화에 실패해 원문으로 검색합니다: {type(error).__name__}")
            return schemas.ResumeProfileOut(
                search_query=request.resume_text[:2000],
                target_roles=[],
                skills=[],
                career_years=request.career_years,
                summary="",
            )

    # ── ③ 하드 필터용 프로필 ─────────────────────────
    @staticmethod
    def to_resume_profile(
        request: schemas.RecommendRequest, profile: schemas.ResumeProfileOut
    ) -> ResumeProfile:
        return ResumeProfile(
            resume_id="api",
            target_roles=profile.target_roles,
            skills=profile.skills,
            project_skills=profile.skills,
            preferred_regions=request.preferred_regions,
            preferred_employment_types=request.preferred_employment_types,
            education_level=request.education_level,
            career_years=int(max(request.career_years, profile.career_years)),
            majors=request.majors,
            certifications=request.certifications,
        )

    @staticmethod
    def hit_to_job(hit: retrieval.Hit) -> Job:
        """검색 결과 메타데이터를 하드 필터가 읽는 Job으로. 원문은 excerpt만 있다."""
        meta = hit.metadata
        years = meta.get("min_career_years")
        return Job(
            job_id=hit.job_id,
            source=str(meta.get("source", "")),
            source_job_id=hit.job_id.split("-")[-1],
            source_url=str(meta.get("source_url", "")),
            company=str(meta.get("company", "")),
            company_type="",
            title=str(meta.get("title", "")),
            description=str(meta.get("excerpt", "")),
            required_skills=list(meta.get("required_skills") or []),
            preferred_skills=list(meta.get("preferred_skills") or []),
            tech_stack=list(meta.get("tech_stack") or []),
            career_type=str(meta.get("career_type", "ANY")),
            min_career_years=None if years in (None, -1) else int(years),
            education=str(meta.get("education", "미기재")),
            region=str(meta.get("region_text", "미기재")),
            employment_type=str(meta.get("employment_type", "미기재")),
            posted_at=None,
            deadline=(meta.get("deadline") or None),
            status=str(meta.get("status", "OPEN")),
            content_hash=str(meta.get("content_hash", "")),
            parser_version="api",
            field_provenance={},
            body_is_image=bool(meta.get("body_is_image", False)),
        )

    @staticmethod
    def _load_reviewable_hits(hits: list[retrieval.Hit], warnings: list[str]) -> list[tuple[retrieval.Hit, Job]]:
        """Use the full-text store as the authority for cards that can open review.

        Pinecone can briefly retain a vector from a prior ingestion snapshot. Returning
        that metadata as a recommendation lets a user select an ID that the detailed
        review service cannot load. Resolve every hit against the SQLite source before
        it reaches the UI so recommendation and review share one job snapshot.
        """
        from job_matching_bot.ingest import DEFAULT_STORE
        from job_matching_bot.ingestion.sqlite_store import SqliteJobStore

        if not DEFAULT_STORE.is_file():
            raise SearchUnavailable('공고 원문 저장소를 찾을 수 없습니다.')
        resolved: list[tuple[retrieval.Hit, Job]] = []
        missing = inactive = 0
        with SqliteJobStore(DEFAULT_STORE) as store:
            for hit in hits:
                record = store.get(hit.job_id)
                if record is None:
                    missing += 1
                    continue
                if record.status != 'OPEN':
                    inactive += 1
                    continue
                resolved.append((hit, record.job))
        if missing:
            warnings.append(f'원문 저장소에 없는 이전 검색 결과 {missing}건을 제외했습니다.')
        if inactive:
            warnings.append(f'마감 또는 비활성 공고 {inactive}건을 제외했습니다.')
        return resolved

    # ── ④ 재정렬 ─────────────────────────────────────
    @staticmethod
    def _job_payload(job: Job) -> dict[str, str]:
        return {
            "job_id": job.job_id,
            "company": job.company,
            "title": job.title,
            "conditions": f"{job.region} · {job.career_type} · {job.employment_type} · {job.education}",
            "body": job.description[:JOB_EXCERPT_CHARS],
        }

    def rerank(
        self, resume_text: str, candidates: list[tuple[retrieval.Hit, Job, dict]], warnings: list[str]
    ) -> tuple[dict[str, schemas.JobFit], bool]:
        """공고를 한 건씩 **동시에** 판정한다.

        예전에는 6건을 한 프롬프트에 넣어 한 번 불렀다. 모델이 순서대로 처리하므로
        시간이 건수에 비례해 늘었다(실측 28.8초, 1건만이면 9.3초). 나눠서 동시에 부르면
        가장 느린 한 건만큼만 기다린다. 판정은 공고마다 독립이라 나눠도 결과가 달라지지 않는다.

        한 건이 실패해도 나머지는 살린다. 전부 실패했을 때만 검색 순서로 물러난다.
        """
        if not candidates:
            return {}, False

        def judge(job: Job) -> schemas.RerankOut:
            return self.reranker(
                {
                    "resume_text": resume_text,
                    "jobs": json.dumps([self._job_payload(job)], ensure_ascii=False, indent=2),
                }
            )

        fits: dict[str, schemas.JobFit] = {}
        failures: list[str] = []
        with ThreadPoolExecutor(max_workers=len(candidates)) as pool:
            futures = {pool.submit(judge, job): job for _, job, _ in candidates}
            for future in as_completed(futures):
                job = futures[future]
                try:
                    for fit in future.result().results:
                        fits[fit.job_id] = fit
                except Exception as error:
                    failures.append(f"{job.job_id}({type(error).__name__})")

        if failures:
            warnings.append(f"일부 공고를 분석하지 못해 검색 순서로 표시합니다: {', '.join(failures)}")
        return fits, bool(fits)

    # ── ⑤ 근거 검증 ──────────────────────────────────
    @staticmethod
    def verify(fit: schemas.JobFit, resume_text: str, job: Job, warnings: list[str]) -> schemas.JobFit:
        """모델이 낸 인용이 양쪽 원문에 실제로 있는지 대조한다.

        공백만 다른 경우까지 지어낸 것으로 보면 안 된다. 사람인 공고 본문에는
        ` `(줄바꿈 없는 공백)과 줄바꿈이 섞여 있어, 모델이 같은 문장을 옮겨 적어도
        정확 일치가 깨진다. 실측에서 실패한 인용 6건 중 5건이 이 경우였다.
        그래서 공백을 하나로 접어 비교하되, **글자는 그대로여야 한다.**
        """
        kept: list[schemas.Reason] = []
        for reason in fit.reasons:
            if not _quote_in(reason.resume_quote, resume_text):
                warnings.append(f"이력서에 없는 인용을 제거했습니다: {reason.resume_quote[:40]}")
                continue
            if not _quote_in(reason.job_quote, job.description):
                warnings.append(f"공고에 없는 인용을 제거했습니다: {reason.job_quote[:40]}")
                continue
            kept.append(reason)

        fit = fit.model_copy(update={"reasons": kept})
        if not kept and fit.fit != "낮음":
            # 근거를 하나도 못 대면 "낮음"이다. 이유 없이 추천 목록에 올리지 않는다.
            fit = fit.model_copy(update={"fit": "낮음"})
        return fit

    # ── 전체 ─────────────────────────────────────────
    def recommend(
        self,
        request: schemas.RecommendRequest,
        progress: Callable[[str, str | None], None] | None = None,
    ) -> schemas.RecommendResponse:
        """`progress`를 주면 단계가 바뀔 때마다 부른다.

        추천은 15초쯤 걸린다. 그동안 앱이 보여 줄 것이 막대 하나뿐이라 무엇이 진행 중인지
        알 수 없었다. 단계마다 알려 주면 앱이 그대로 보여 줄 수 있다.

        부르는 규칙은 둘뿐이다. 단계를 **시작**할 때 `progress(이름, None)`, **끝낼** 때
        `progress(이름, 결과 한 줄)`. 결과 줄은 그대로 화면에 나가므로 숫자를 담는다.
        진행 알림이 추천을 막으면 안 되므로 실패는 삼킨다.
        """
        say = _progress_reporter(progress)
        warnings: list[str] = []
        clock = StageClock()
        # 구조화가 0초면 앱이 보냈거나 캐시에서 꺼낸 것이다. 시간만 보고는 모르므로 같이 적는다.
        if request.profile is not None:
            profile_source = "앱"
        elif request.resume_text in self._profiles:
            profile_source = "캐시"
        else:
            profile_source = "LLM"

        def finish(response: schemas.RecommendResponse) -> schemas.RecommendResponse:
            timings = clock.timings()
            print(format_timings(timings, profile_source))
            return response.model_copy(
                update={"timings_ms": timings, "profile_source": profile_source}
            )

        say("resume")
        profile = self.build_profile(request, warnings)
        clock.lap("profile")
        say("resume", f"기술 {len(profile.skills)}개 · 직무 {len(profile.target_roles)}개를 뽑았어요")

        say("search")
        try:
            hits = retrieval.search(
                profile.search_query,
                SEARCH_TOP_K,
                retrieval.build_filter(
                    request.preferred_regions,
                    request.preferred_employment_types,
                    max(request.career_years, profile.career_years),
                ),
            )
        except Exception as error:
            reason = str(error).strip()
            if not reason or len(reason) > 180:
                reason = type(error).__name__
            raise SearchUnavailable(f"공고 검색에 실패했습니다: {reason}") from error
        clock.lap("search")
        say("search", f"열린 공고에서 {len(hits)}건을 추렸어요")
        if not hits:
            return finish(schemas.RecommendResponse(
                recommendations=[],
                search_query=profile.search_query,
                profile_summary=profile.summary,
                reranked=False,
                warnings=[*warnings, "조건에 맞는 공고를 찾지 못했습니다."],
            ))

        say("filter")
        resume_profile = self.to_resume_profile(request, profile)
        candidates: list[tuple[retrieval.Hit, Job, dict]] = []
        try:
            for hit, job in self._load_reviewable_hits(hits, warnings):
                result = hard_filter(job, resume_profile)
                if result["status"] == "FAIL":
                    continue
                candidates.append((hit, job, result))
        except Exception as error:
            raise SearchUnavailable(f"조건 판정에 실패했습니다: {type(error).__name__}") from error
        clock.lap("filter")

        # 판정 **전에** 거른다. 내려간 공고에 LLM을 쓸 이유가 없다. 자르기는 그
        # 다음이다 — 먼저 잘라 버리면 마감된 만큼 자리가 비고 뒤 후보가 올라오지
        # 못한다. 확인 대상이 늘지만(최대 25건) 한 번에 여는 요청이라 시간은 같다.
        # 마감 시각이 이미 지난 공고는 열어 볼 것 없이 뺀다(검색은 날짜만 견준다).
        alive = self.drop_dead([
            hit.job_id for hit, job, _ in candidates
            if not store_search.deadline_passed(job.deadline)
        ])
        if len(alive) < len(candidates):
            warnings.append(f"마감된 공고 {len(candidates) - len(alive)}건을 제외했습니다.")
            candidates = [c for c in candidates if c[0].job_id in alive]
        clock.lap("liveness")
        # 벡터 순위와 기술 겹침을 섞어 다시 세운다. 벡터 유사도는 후보 안에서 거의
        # 평평해서(실측 폭 0.042~0.140) 그 순서만으로는 누구를 LLM에 보낼지 가리기
        # 어렵다. 기술 정보가 없는 공고는 제자리에 남는다 — `pre_ranker` 참고.
        matches = [skill_match(job, profile.skills) for _, job, _ in candidates]
        # 공고가 우대한다고 적은 자격증·전공을 가졌으면 조금 얹는다. 못 맞췄다고
        # 빼지는 않는다 — 우대사항은 없어도 지원에 지장이 없다.
        preferred = [
            preferred_match(job, resume_profile.certifications, resume_profile.majors)
            for _, job, _ in candidates
        ]
        candidates = pre_rank(
            candidates, [hit.score for hit, _, _ in candidates], matches, preferred
        )
        candidates = candidates[:RERANK_TOP_K]
        clock.lap("pre_rank")
        say("filter", f"조건을 통과한 {len(candidates)}건이 남았어요")

        say("judge")
        fits, reranked = self.rerank(request.resume_text, candidates, warnings)
        clock.lap("rerank")

        # 같은 적합도 안에서는 다시 세운 순서를 쓴다. 예전에는 벡터 순위였는데,
        # 판정을 예측하는 힘이 더 약한 신호였다(+0.26 대 +0.42).
        rows: list[tuple[int, int, schemas.Recommendation]] = []
        for position, (hit, job, filter_result) in enumerate(candidates):
            fit = fits.get(job.job_id)
            if fit is not None:
                fit = self.verify(fit, request.resume_text, job, warnings)
            rows.append(
                (
                    fit_order(fit.fit if fit else None),
                    position,
                    schemas.Recommendation(
                        job_id=job.job_id,
                        company=job.company,
                        title=job.title,
                        source_url=job.source_url,
                        # 판정을 못 받은 공고는 '보통'으로 올려 보내지 않는다. 판정된
                        # '낮음'보다 위에 서는 것이 말이 안 된다. 가장 낮게 두고 사유를 남긴다.
                        fit=fit.fit if fit else "낮음",
                        reasons=fit.reasons if fit else [],
                        concerns=fit.concerns if fit else [UNJUDGED_CONCERN],
                        conditions=schemas.Conditions(
                            region=job.region,
                            employment_type=job.employment_type,
                            career=_career_label(job),
                            education=job.education,
                            deadline=job.deadline,
                        ),
                        filter_status=filter_result["status"],
                        unknown_conditions=filter_result["unknown"],
                        passed_conditions=filter_result["passed"],
                        search_rank=hit.rank,
                        body_is_image=job.body_is_image,
                    ),
                )
            )

        say("judge", f"{len(rows)}건의 근거를 맞대어 봤어요")
        rows.sort(key=lambda r: (r[0], r[1]))
        limited = _limit_per_company(row[2] for row in rows)
        clock.lap("verify")
        return finish(schemas.RecommendResponse(
            recommendations=limited[: request.top_k],
            search_query=profile.search_query,
            profile_summary=profile.summary,
            reranked=reranked,
            warnings=_deduplicate(warnings),
        ))


_WHITESPACE = re.compile(r"\s+")


def _normalize_quote(text: str) -> str:
    """공백을 하나로 접는다. ` ` 같은 특수 공백도 일반 공백으로 본다."""
    return _WHITESPACE.sub(" ", (text or "").replace(" ", " ")).strip()


def _quote_in(quote: str, source: str) -> bool:
    """인용이 원문에 있는가. 공백 차이는 무시하고 글자만 본다."""
    normalized = _normalize_quote(quote)
    if not normalized:
        return False
    return normalized in _normalize_quote(source)


def _resolve_job_refs(refs: list[int], last_job_ids: list[str]) -> list[str]:
    """가리킨 자리를 모두 job_id로 바꾼다. 범위를 벗어난 번호는 버린다.

    같은 번호를 두 번 말해도 한 번만 담는다. "1번하고 1번 비교해줘"는 비교가 아니다.
    """
    found: list[str] = []
    for ref in refs:
        if 1 <= ref <= len(last_job_ids):
            job_id = last_job_ids[ref - 1]
            if job_id not in found:
                found.append(job_id)
    return found


def _resolve_job_ref(refs: list[int], last_job_ids: list[str]) -> str | None:
    """"2번"을 직전 목록의 job_id로 바꾼다. 가리킨 자리가 없으면 None.

    서버는 대화를 저장하지 않는다. 직전에 무엇을 보여 줬는지는 앱이 `last_job_ids`로
    되돌려 줘야 안다. 그래서 목록을 안 받았거나 범위를 벗어난 번호는 조용히 넘긴다 —
    엉뚱한 공고를 집는 것보다 못 알아들었다고 하는 편이 낫다.

    여러 개를 가리켰으면 첫 번째만 쓴다. 비교는 아직 못 한다.
    """
    for ref in refs:
        if 1 <= ref <= len(last_job_ids):
            return last_job_ids[ref - 1]
    return None


def _career_label(job: Job) -> str:
    if job.career_type == "ENTRY":
        return "신입"
    if job.career_type == "ANY":
        return "경력무관"
    if job.career_type == "EXPERIENCED":
        return "경력" if job.min_career_years is None else f"경력 {job.min_career_years}년 이상"
    return "미기재"


def _limit_per_company(rows) -> list[schemas.Recommendation]:
    """한 회사가 목록을 채우지 않게 상한을 둔다.

    지점별·연차별로 나눠 올린 공고가 본문이 같아 나란히 올라오는 일이 있다.
    """
    seen: dict[str, int] = defaultdict(int)
    kept: list[schemas.Recommendation] = []
    for row in rows:
        if seen[row.company] >= MAX_PER_COMPANY:
            continue
        seen[row.company] += 1
        kept.append(row)
    return kept


def _deduplicate(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


# ── 공고 찾아보기 챗봇 ───────────────────────────────────
class ChatService(_LivenessMixin):
    """말을 받아 세 갈래로 답한다.

        검색   "서울 백엔드 신입 찾아줘"   → 저장소 조회, 목록
        질문   "백엔드 신입은 뭘 준비해?"  → 조건에 맞는 공고를 세어 그 숫자로 답
        공고   (목록에서 하나 고른 뒤)      → 그 공고 원문만 근거로 답

    추천과 다른 점이 둘이다. 첫째, 이력서가 아니라 **사용자가 말한 조건**으로 찾으므로
    벡터가 필요 없다. 둘째, Pinecone이 아니라 저장소를 보므로 IT 밖 공고도 답할 수 있다.

    LLM 호출 수를 갈래마다 다르게 둔다. 검색은 한 번(말→조건)이고 답 문장은 실제 결과로
    조립한다. 건수를 모르는 채 LLM이 쓰면 없는 공고를 있다고 말한다. 질문·공고는 두
    번째 호출로 답을 쓰되 **근거를 함께 준다** — 질문에는 공고를 센 표를, 공고에는 그
    공고 원문을. 근거 없이 쓰게 하면 어디서나 들을 수 있는 말이 나온다.

    대화를 서버에 저장하지 않는다. 직전 조건을 응답에 실어 보내고 앱이 되돌려준다.
    """

    def __init__(self, generator=None, store_path: Path | None = None,
                 adviser=None, job_asker=None, finder=None, comparer=None):
        self._generator = generator
        self._store_path = store_path
        self._adviser = adviser
        self._job_asker = job_asker
        self._finder = finder
        self._comparer = comparer

    @property
    def comparer(self):
        """공고 둘을 맞대어 답을 쓰는 함수."""
        if self._comparer is None:
            from job_matching_bot.api.prompts_compare import JOB_COMPARE_PROMPT

            self._comparer = _build_generator(JOB_COMPARE_PROMPT, schemas.ChatAnswerOut)
        return self._comparer

    @property
    def finder(self):
        """뜻으로 찾는 함수. 인덱스를 실제로 부르므로 테스트에서는 갈아끼운다."""
        if self._finder is None:
            from job_matching_bot.retrieval import search as retrieval

            self._finder = retrieval.search
        return self._finder

    @property
    def generator(self):
        """말을 가르고 조건을 뽑는 호출. 모든 말이 여기를 지난다(`CHAT_EFFORT` 참고)."""
        if self._generator is None:
            self._generator = _build_generator(
                prompts.CHAT_PROMPT, schemas.ChatTurnOut, effort=CHAT_EFFORT
            )
        return self._generator

    @property
    def adviser(self):
        if self._adviser is None:
            self._adviser = _build_generator(prompts.ADVICE_PROMPT, schemas.ChatAnswerOut)
        return self._adviser

    @property
    def job_asker(self):
        if self._job_asker is None:
            self._job_asker = _build_generator(prompts.JOB_ASK_PROMPT, schemas.ChatAnswerOut)
        return self._job_asker

    @property
    def store_path(self) -> Path:
        if self._store_path is None:
            from job_matching_bot.ingest import DEFAULT_STORE

            self._store_path = DEFAULT_STORE
        return self._store_path

    def chat(self, request: schemas.JobChatRequest) -> schemas.JobChatResponse:
        """말 한 마디에 답한다. 지난 단계마다 걸린 시간을 로그와 응답에 남긴다.

        갈래마다 LLM을 부르는 횟수가 달라(0~2번) 요청 전체 시간만으로는 어디가
        느린지 알 수 없다.
        """
        if not self.store_path.exists():
            raise StoreUnavailable("공고 저장소가 없습니다. 공유 파일을 먼저 받아 주세요.")
        clock = StageClock()
        response = self._chat(request, clock)
        timings = clock.timings()
        print(format_chat_timings(timings, response.mode))
        return response.model_copy(update={"timings_ms": timings})

    def _chat(self, request: schemas.JobChatRequest, clock: StageClock) -> schemas.JobChatResponse:
        previous = request.filters or schemas.ChatFilters()

        # 모델을 부르기 전에 막는 한 겹. 여기 걸리면 호출이 0이다.
        # 적어 둔 말만 잡는다. 나머지는 아래에서 모델이 가른다(`off_topic`).
        if abuse.is_abuse(request.message):
            return schemas.JobChatResponse(
                mode="안내",
                reply=OFF_TOPIC_REPLY,
                filters=previous,
                total=0,
                suggestions=["서울 백엔드 신입", "요즘 많이 요구하는 기술이 뭐야?"],
            )

        # 공고를 골라 물은 경우. 무슨 말이든 그 공고에 대한 물음이므로 의도를 가르지 않는다.
        if request.job_id:
            return self._ask_job(request, previous, clock)

        turn = self.generator(
            {
                "previous": previous.model_dump_json(),
                "message": request.message,
            }
        )
        clock.lap("route")

        # 여기가 문이다. **채용이라고 짚은 말만** 아래로 내려간다.
        #
        # 막을 것을 고르는 대신 답해도 되는 것을 짚게 했다. 애매한 말은 통과하지 않고
        # 막힌다. 아래 어느 단계도 모델이 쓴 문장을 쓰지 않으므로, 답하지 말아야 할
        # 것에 답할 길이 없다.
        if turn.topic == "그 밖":
            return schemas.JobChatResponse(
                mode="안내",
                reply=OFF_TOPIC_REPLY,
                filters=previous,
                total=0,
                suggestions=["서울 백엔드 신입", "요즘 많이 요구하는 기술이 뭐야?"],
            )
        if turn.topic == "인사":
            return self._small_talk(turn, previous)

        # "2번 자세히 봐줘" — 직전 목록에서 자리를 가리킨 말. 그 공고 하나에 대한 물음이
        # 되므로 조건 검색으로 내려보내지 않는다. 사용자가 카드를 다시 누르지 않아도 된다.
        # 자리를 **둘 이상** 가리켰으면 비교다. 따로 의도를 두지 않는다 — 개수가 곧
        # 신호이고, LLM이 한 번 더 가를 일을 만들지 않는 편이 틀릴 여지가 적다.
        picked_many = _resolve_job_refs(turn.job_refs, request.last_job_ids)
        if len(picked_many) >= 2:
            return self._compare_jobs(request, previous, picked_many[:2], clock)
        if picked_many:
            return self._ask_job(
                request.model_copy(update={"job_id": picked_many[0]}), previous, clock
            )
        # "두 공고의 자격요건만" — 번호 없이 방금 이야기한 공고를 가리킨 말. 비교 뒤에
        # 이어지는 물음이 대부분 이 꼴이라, 여기서 못 받으면 챗봇이 스스로 내놓은
        # 제안을 눌렀는데 "공고가 보이지 않아 비교할 수 없다"고 답하게 된다.
        if turn.refers_to_last_answer and request.last_answer_job_ids:
            discussed = list(request.last_answer_job_ids)
            if len(discussed) == 2:
                return self._compare_jobs(request, previous, discussed, clock)
            if len(discussed) == 1:
                return self._ask_job(
                    request.model_copy(update={"job_id": discussed[0]}), previous, clock
                )
            # 셋 이상이면 어느 것인지 고를 수 없다. 앞의 둘을 집으면 사용자가 생각한
            # 공고가 아닐 수 있고, 답은 그럴듯해서 틀린 줄도 모른다.
            return schemas.JobChatResponse(
                mode="안내",
                reply="어느 공고를 말씀하시는지 번호로 알려 주세요. 예를 들어 “1번하고 3번 비교해줘”처럼요.",
                filters=previous,
                total=0,
                suggestions=["1번 자세히 봐줘", "1번하고 2번 비교해줘"],
            )

        if (turn.job_refs or turn.refers_to_last_answer) and not request.last_job_ids:
            return schemas.JobChatResponse(
                mode="안내",
                reply="앞에 보여 드린 공고가 없어요. 먼저 조건을 말씀해 주시면 목록을 보여 드릴게요.",
                filters=previous,
                total=0,
                suggestions=["서울 백엔드 신입", "마감 임박한 공고"],
            )

        if turn.unavailable:
            return self._unavailable(turn.unavailable, previous)

        if turn.intent == "잡담":
            return self._small_talk(turn, previous)

        if turn.intent == "추천":
            # 챗봇은 이력서를 받지 않는다. 앱이 이 mode를 보고 추천으로 넘긴다.
            # 여기서 검색을 하면 앞 대화에 남은 조건으로 엉뚱한 목록이 나간다.
            source = {
                "프로젝트": "이력서의 프로젝트 경험만",
                "기술스택": "이력서의 기술스택만",
                "자기소개서": "이력서의 자기소개서만",
                "경력": "이력서의 경력만",
            }.get(turn.resume_scope, "이력서를")
            return schemas.JobChatResponse(
                mode="추천",
                resume_scope=turn.resume_scope,
                reply=f"{source} 읽고 맞는 공고를 골라 드릴게요.",
                filters=previous,
                total=0,
            )

        filters = _to_job_filters(turn.filters)

        if turn.intent == "질문":
            return self._advise(request, turn, filters, clock)

        # 조건이 하나도 안 잡혔다고 바로 되묻지 않는다. "돈 다루는 일"처럼 조건으로
        # 옮길 말이 없는 경우가 있고, 그때는 뜻으로 찾으면 된다. 되묻는 것은 뜻으로
        # 찾을 문장마저 없을 때다.
        if filters.is_empty and not turn.requirement_query:
            return schemas.JobChatResponse(
                mode="안내",
                reply=turn.understood or "어떤 일을 찾으시는지 알려 주세요. 예: 데이터 분석 신입",
                filters=turn.filters,
                total=0,
            )

        # "이거 말고" — 같은 조건에서 앱이 지금까지 보여 준 공고를 빼고 다음 것을 준다.
        # 직전 한 쪽만 빼면 두 번째 "이거 말고"에 첫 목록이 다시 나오므로 전부 받는다.
        more = turn.show_more and bool(request.seen_job_ids)
        seen = request.seen_job_ids if more else []

        result = (
            store_search.SearchResult(jobs=[], total=0, scanned_cap=False, strong=0)
            if filters.is_empty
            else store_search.search(
                self.store_path, filters, limit=request.top_k, exclude_ids=seen
            )
        )
        clock.lap("search")

        # 조건으로 못 찾았으면 뜻으로 찾는다. 사용자가 말한 직무·기술이 공고에 그대로
        # 적히는 말이 아닐 때(예: "돈 다루는 일") 여기서만 답이 나온다.
        by_meaning = False
        if turn.requirement_query and self._needs_meaning(filters, result):
            found = self._by_meaning(turn.requirement_query, filters, request.top_k, seen)
            if found:
                result = store_search.SearchResult(
                    jobs=found, total=len(found), scanned_cap=False, strong=0
                )
                by_meaning = True
            clock.lap("meaning")

        # 보여 주기 직전에 내려간 공고를 뺀다. 저장소가 OPEN이라고 해도 사이트에서
        # 이미 마감됐을 수 있다 — 그건 열어 봐야만 안다.
        #
        # 보내기 직전에 두 가지를 본다. 마감 **시각**이 지났나(조회는 날짜만 견준다), 그리고
        # 사이트에서 조기 마감됐나. 시각이 지난 공고는 페이지를 열 것도 없이 뺀다.
        shown = result.jobs
        if shown:
            now = datetime.now(store_search.KST)
            open_now = [hit for hit in shown if not store_search.deadline_passed(hit.deadline, now)]
            alive = set(self.drop_dead([hit.job_id for hit in open_now]))
            kept = [hit for hit in open_now if hit.job_id in alive]
            if len(kept) < len(shown):
                gone = [hit for hit in shown if hit.job_id not in alive]
                result = store_search.SearchResult(
                    jobs=kept,
                    total=max(result.total - len(gone), len(kept)),
                    scanned_cap=result.scanned_cap,
                    # 빠진 것 중 직접 맞은 공고만큼 뺀다. 예전에는 보여 줄 수로 잘라
                    # "247건"이 "4건"으로 줄어 답에 나갈 뻔했다.
                    strong=max(result.strong - sum(1 for hit in gone if hit.relevance >= 2), 0),
                    skipped=result.skipped,
                )
                shown = kept
            clock.lap("liveness")

        return schemas.JobChatResponse(
            reply=self._reply(turn.understood, filters, result, by_meaning, more=more),
            filters=turn.filters,
            jobs=[_to_chat_job(hit) for hit in shown],
            # 답이 말한 건수와 같게 둔다. 제목·태그에 직접 맞은 공고가 있으면 그 수다.
            total=result.total if by_meaning else (result.strong or result.total),
            suggestions=_suggestions(filters, result),
        )

    @staticmethod
    def _small_talk(turn, previous) -> schemas.JobChatResponse:
        """인사에는 인사로. **모델을 한 번 더 부르지 않는다.**

        "안녕"에 사용법 안내가 돌아오면 사람과 말하는 것 같지 않다. 그렇다고 답을 쓰는
        호출을 붙이면 인사 한 마디에 두 번을 부르게 된다. 갈래를 가르며 이미 받아 둔
        `understood`를 그대로 쓴다.
        """
        return schemas.JobChatResponse(
            mode="안내",
            reply=turn.understood.strip() or SMALL_TALK_FALLBACK,
            filters=previous,
            total=0,
            suggestions=["서울 백엔드 신입", "요즘 많이 요구하는 기술이 뭐야?"],
        )

    @staticmethod
    def _unavailable(kind: str, previous) -> schemas.JobChatResponse:
        """모으지 않는 것으로 찾아 달라고 했다. 없다고 말하고 할 수 있는 것을 권한다.

        "조건을 빼 보라"고 하면 안 된다. 빼면 찾을 수 있다는 뜻인데 그렇지 않다.
        왜 없는지도 밝힌다. 그래야 사용자가 다른 데서 찾아본다.
        """
        return schemas.JobChatResponse(
            mode="안내",
            reply=_UNAVAILABLE[kind],
            filters=previous,
            total=0,
            suggestions=_UNAVAILABLE_NEXT[kind],
        )

    @staticmethod
    def _needs_meaning(filters, result) -> bool:
        """조건 검색이 실패했나. 실패에 두 가지가 있다.

        하나는 0건이고, 하나는 **제목·태그에 하나도 안 걸린 것**이다. 후자는 본문에
        말이 스친 범용 공고("전 직군 공개채용")만 걸린 경우라, 건수는 많아도 물어본
        일과 상관이 없다.

        조건이 아예 안 잡힌 경우도 실패다. "돈 다루는 일"은 조건으로 옮길 말이 없어
        LLM이 비워 둔다. 그때는 뜻으로 찾는 수밖에 없다.

        다만 지역·경력만 걸었으면(찾을 말이 없으면) 조건 조회가 정확하므로 뜻으로 찾지
        않는다. 이걸 빼먹으면 "서울만" 같은 말에도 매번 벡터를 부르게 된다.
        """
        if filters.is_empty:
            return True
        if not (filters.roles or filters.skills or filters.keywords):
            return False
        return result.total == 0 or result.strong == 0

    def _by_meaning(self, query: str, filters, top_k: int, seen: list[str] = ()) -> list:
        """뜻이 가까운 공고. 인덱스에서 찾아 저장소에서 다시 읽는다.

        여기서 실패해도 대화를 끊지 않는다. 조건 검색 결과가 이미 있고, 없으면 없다고
        답하면 된다. 인덱스가 안 붙었다고 챗봇 전체가 멈출 이유가 없다.

        `seen`은 "이거 말고"로 넘겨 보는 중에 이미 보여 준 공고다. 그만큼 더 가져와 뺀다.
        """
        from job_matching_bot.retrieval import search as retrieval

        try:
            condition = retrieval.build_filter(
                # 인덱스 메타의 지역은 시·도다. "분당구"처럼 좁게 말한 지역은 여기서 못 걸고
                # 아래에서 주소 글자로 거른다.
                regions=[region for region in filters.regions if region in market_stats.SIDO],
                employment_types=filters.employment_types,
                # 신입이라고 했을 때만 경력 하한을 건다. 나머지는 걸지 않는다.
                career_years=0 if filters.career == "신입" else 5,
            )
            # 마감된 것이 걸러져 줄어드므로 넉넉히 가져온다.
            hits = self.finder(query, top_k=min(top_k * 3 + len(seen), 100), filter=condition)
        except Exception as error:
            print(f"[챗봇] 의미 검색 실패, 조건 결과로 답한다: {type(error).__name__}: {error}")
            return []
        skip = set(seen)
        found = store_search.by_ids(
            self.store_path, [hit.job_id for hit in hits if hit.job_id not in skip]
        )
        if filters.regions:
            # 조건 조회와 같은 잣대로 본다(`region LIKE %지역%`). 시·도만 걸린 벡터 검색이
            # 판교를 물었는데 용인 공고를 가져와도 여기서 빠진다.
            found = [
                hit for hit in found
                if "전국" in (hit.region or "") or any(r in (hit.region or "") for r in filters.regions)
            ]
        return found[:top_k]

    def _advise(self, request, turn, filters, clock: StageClock) -> schemas.JobChatResponse:
        """채용 질문에 답한다. 조건이 잡혔으면 그 조건의 공고를 세어 근거로 준다.

        "백엔드 신입은 뭘 준비해?"는 셀 수 있고 "자소서 어떻게 써?"는 셀 것이 없다.
        후자에 표를 주면 상관없는 숫자가 답의 첫 문단을 차지한다. 조건이 남아 있느냐가
        아니라 **이번 물음이 세어서 답할 것이냐**로 가른다. 그 판정은 조건을 뽑을 때
        같이 받아 두므로 LLM을 더 부르지 않는다.

        조건이 비어 있어도 센다. "요즘 많이 요구하는 기술이 뭐야?"에는 조건이 없지만
        **전체를 세면** 답이 나온다. 조건이 없다고 세지 않았더니 세어 달라는 질문에
        "저희가 모은 공고로는 알 수 없어요"라고 답했다.
        """
        stats = None
        if turn.counts_jobs:
            stats = market_stats.summarize(self.store_path, filters)
            clock.lap("stats")
        grounded = bool(stats and stats.total)

        answer = self.adviser(
            {
                "condition": filters.summary(),
                "stats": stats.to_prompt() if grounded else "(이 물음은 공고를 세어 답할 것이 아니다)",
                "question": request.message,
            }
        )
        clock.lap("answer")
        # 근거 공고를 붙이지 않는다. 예전에는 숫자를 확인하라고 3건을 붙였는데, 사람이
        # 답을 매겨 보니 "요즘 AI 공고는 뭘 요구해?" 같은 답에는 공고가 필요 없었다.
        # 그 3건을 찾고 마감을 확인하느라 쓰던 시간도 줄어든다. 공고를 보고 싶으면
        # 답의 이어 물을 말("이 조건으로 공고 보여줘")로 검색하면 된다.
        return schemas.JobChatResponse(
            mode="질문",
            reply=answer.answer,
            filters=turn.filters,
            total=stats.total if grounded else 0,
            suggestions=answer.followups[:3],
        )

    def _ask_job(self, request, previous, clock: StageClock) -> schemas.JobChatResponse:
        """공고 하나를 놓고 묻는다. 그 공고 원문만 근거로 쓴다."""
        from job_matching_bot.ingestion.sqlite_store import SqliteJobStore

        with SqliteJobStore(self.store_path) as store:
            record = store.get(request.job_id)
            listing = None if record is not None else store.get_listing(request.job_id)
        clock.lap("store")
        if record is None:
            # 목록에서만 본 공고다. 마감된 것이 아니라 아직 상세를 안 받은 것이므로
            # 그렇게 말하고 원문으로 보낸다. 없는 내용을 지어내지 않는다.
            if listing is not None:
                return self._listing_only(listing, previous)
            return schemas.JobChatResponse(
                mode="안내",
                reply="그 공고를 저장소에서 찾지 못했어요. 마감되어 내려갔을 수 있어요.",
                filters=previous,
                total=0,
            )

        # 마감됐는지 확인한다. 마감 시각이 지났으면 열어 볼 것도 없다. 시각이 남아 있어도
        # 회사가 채용을 마치면 먼저 닫으므로 페이지를 본다. 방금 확인한 공고면 캐시가 있어
        # 요청이 안 나간다(`liveness.TTL_HOURS`).
        passed = store_search.deadline_passed(record.job.deadline)
        alive = [] if passed else self.drop_dead([request.job_id])
        clock.lap("liveness")
        if not alive:
            return schemas.JobChatResponse(
                mode="안내",
                reply="그 공고는 접수가 마감됐어요. 다른 공고를 찾아 드릴까요?",
                filters=previous,
                total=0,
                suggestions=["비슷한 공고 더 보여줘"],
            )

        # 이력서를 함께 받았으면 넘긴다. 이력서 화면에서 "나한테 맞아?"라고 물었는데
        # 공고만 읽고 "이력서를 볼 수 없어요"라고 답하던 것을 고친다.
        resume = (request.resume_text or "").strip()
        answer = self.job_asker(
            {
                "job": _job_text(record.job),
                "resume": resume or "(없음)",
                "question": _without_ordinal(request.message),
            }
        )
        clock.lap("answer")
        return schemas.JobChatResponse(
            mode="공고",
            reply=answer.answer,
            filters=previous,
            # 어느 공고를 두고 답했는지 함께 보낸다. 없으면 화면이 답만 띄우고
            # 사용자는 그게 자기가 가리킨 공고인지 확인할 길이 없다.
            jobs=[_job_to_chat_job(record.job)],
            total=1,
            suggestions=answer.followups[:3],
        )

    def _compare_jobs(
        self, request, previous, job_ids: list[str], clock: StageClock
    ) -> schemas.JobChatResponse:
        """공고 둘을 맞대어 답한다. 두 공고 원문과 이력서만 근거로 쓴다.

        마감된 공고를 비교하면 답이 헛돈다. 사용자가 그 공고를 본 뒤 시간이 지났을 수
        있으므로 여기서 다시 확인한다. 한쪽만 살아 있으면 비교가 아니라 그 하나에 대한
        답으로 내려간다 — 없는 공고를 상대로 견주게 하는 것보다 낫다.
        """
        from job_matching_bot.ingestion.sqlite_store import SqliteJobStore

        with SqliteJobStore(self.store_path) as store:
            records = [store.get(job_id) for job_id in job_ids]
        clock.lap("store")
        alive = self.drop_dead([
            r.job.job_id for r in records
            if r is not None and not store_search.deadline_passed(r.job.deadline)
        ])
        clock.lap("liveness")
        live = [r for r in records if r is not None and r.job.job_id in alive]

        if len(live) < 2:
            if len(live) == 1:
                return self._ask_job(
                    request.model_copy(update={"job_id": live[0].job.job_id}), previous, clock
                )
            return schemas.JobChatResponse(
                mode="안내",
                reply="비교할 공고를 찾지 못했어요. 마감되어 내려갔을 수 있어요.",
                filters=previous,
                total=0,
            )

        resume = (request.resume_text or "").strip()
        answer = self.comparer(
            {
                "job_a": _job_text(live[0].job),
                "job_b": _job_text(live[1].job),
                "resume": resume or "(없음)",
                "question": request.message,
            }
        )
        clock.lap("answer")
        return schemas.JobChatResponse(
            mode="비교",
            reply=answer.answer,
            filters=previous,
            jobs=[_job_to_chat_job(r.job) for r in live],
            total=len(live),
            suggestions=answer.followups[:3],
        )

    @staticmethod
    def _listing_only(listing: dict, previous) -> schemas.JobChatResponse:
        """상세를 아직 안 받은 공고. 아는 것만 말하고 원문으로 보낸다."""
        company = listing.get("company") or "이 공고"
        conditions = (listing.get("condition_text") or "").strip()
        return schemas.JobChatResponse(
            mode="공고",
            reply=(
                f"{company}의 “{listing.get('title') or ''}” 공고는 "
                "아직 상세 내용을 받아 오지 못했어요.\n"
                + (f"목록에 적힌 조건은 {conditions} 입니다.\n" if conditions else "")
                + "자격요건과 주요업무는 공고 원문에서 확인해 주세요."
            ),
            filters=previous,
            jobs=[
                schemas.JobChatJob(
                    job_id=listing.get("job_id") or "",
                    company=listing.get("company") or "",
                    title=listing.get("title") or "",
                    source_url=listing.get("source_url") or "",
                    region=listing.get("region") or "미기재",
                    career=store_search._career_label(
                        listing.get("career_type") or "", listing.get("min_career_years")
                    ),
                    employment_type=listing.get("employment_type") or "미기재",
                    deadline=None,
                    tech_stack=[],
                )
            ],
            total=1,
        )

    @staticmethod
    def _reply(understood: str, filters, result, by_meaning: bool = False, more: bool = False) -> str:
        """실제 결과로 답을 만든다. 건수를 모르는 채로 LLM이 쓰면 틀린 말을 하게 된다.

        **라우터가 쓴 한 줄(`understood`)을 붙이지 않는다.** 모델은 알아들은 대로 쓰지, 실제로
        건 조건대로 쓰지 않는다. "스타트업은 빼고"에 뺄 칸이 없는데도 "스타트업을 제외하고
        찾아보겠습니다", "오늘 올라온"에 날짜로 안 걸렀는데도 "오늘 새로 등록된 공고를
        찾아보겠습니다"라고 썼다. 넘겨 볼 때는 같은 목록을 다시 찾아 놓고 "기존 공고는 제외하고"라고
        쓴 적도 있다. 무엇으로 걸렀는지는 `filters.summary()`가 실제 조건으로 말한다.
        """
        condition = filters.summary()
        shown = len(result.jobs)
        if result.total == 0:
            return (
                f"{condition} 조건으로는 열려 있는 공고를 찾지 못했어요. "
                "조건을 하나 빼거나 지역을 넓혀 보시겠어요?"
            )
        if by_meaning:
            # 어떻게 찾았는지 밝힌다. 조건에 맞는 공고를 센 것처럼 보이면 안 된다.
            if more:
                return f"앞에서 보여드린 공고 말고, 뜻이 가까운 공고를 {shown}건 더 찾았어요."
            found = f"뜻이 가까운 공고를 {shown}건 찾았어요."
            if filters.is_empty:
                return f"말씀하신 말이 공고에 그대로 적히는 말은 아니라서, {found}"
            return f"{condition} 조건 그대로는 걸리는 공고가 없어서, {found}"

        # 말하는 건수는 제목·태그에 직접 맞은 공고다. 본문에 말이 스친 범용 공고까지
        # 세면 실제보다 훨씬 많아 보인다. 직접 맞은 것이 없을 때만 전체를 말한다.
        # "직무가 맞는 건", "관련도" 같은 말은 쓰지 않는다 — 사용자가 알 필요 없는 구분이다.
        count = result.strong or result.total
        capped = result.scanned_cap and not result.strong
        found = (
            f"{condition} 공고가 {count:,}건이 넘어요." if capped
            else f"{condition} 공고 {count:,}건을 찾았어요."
        )

        if more:
            if not shown:
                return (
                    f"{condition} 공고는 앞에서 보여드린 {result.skipped:,}건이 전부예요. "
                    "조건을 바꿔서 찾아볼까요?"
                )
            start, end = result.skipped + 1, result.skipped + shown
            strong = result.strong
            if not strong or end <= strong:
                return f"{condition} 공고 {count:,}건 중 {start:,}~{end:,}번째예요."
            # 직접 맞은 공고를 다 보고 본문에만 스친 공고로 넘어가는 자리. 정렬이 직접
            # 맞은 것을 먼저 세우므로 몇 번째부터인지 셀 수 있다.
            if result.skipped < strong:
                return (
                    f"{condition} 공고 {strong:,}건 중 {start:,}~{strong:,}번째이고, "
                    "그 뒤는 본문에만 언급된 공고예요."
                )
            return (
                f"{condition} 공고 {strong:,}건은 다 보여드렸어요. "
                f"본문에만 언급된 공고 {result.total - strong:,}건 중 "
                f"{start - strong:,}~{end - strong:,}번째예요."
            )

        # 순서는 말하지 않는다. "가까운 순"은 거리 순으로 읽혔고, "제목에 잘 맞는 순"은 태그로 걸린
        # 공고가 맨 앞에 설 때 틀린 말이 됐다. 순서 규칙은 사용자가 알 필요가 없다.
        tail = f" {shown}건 보여드릴게요." if count > shown else ""
        return f"{found}{tail}"


# 모으지 않는 것들. 왜 못 하는지까지 말한다. 실측에 근거한 숫자를 그대로 쓴다.
_UNAVAILABLE = {
    "급여": (
        "급여로는 줄을 세울 수 없어요. 공고 10건 중 9건이 급여를 \u201c면접 후 결정\u201d으로 "
        "적어 두거든요. 남은 1건도 대부분 최저임금 안내라, 급여로 정렬하면 정작 많이 주는 "
        "곳이 빠지고 순서가 거꾸로 나옵니다.\n"
        "대신 직무·지역·경력으로 좁혀 드릴 수 있어요. 급여는 공고를 열어 확인하시는 게 정확합니다."
    ),
    "복지": (
        "복지로 줄을 세우지는 못해요. 공고마다 적는 방식이 달라 비교할 수 있는 값이 아니거든요.\n"
        "찾으시는 조건(재택, 유연근무 같은)을 말씀해 주시면 그 말이 적힌 공고를 찾아 드릴게요."
    ),
    "합격 가능성": (
        "합격 가능성이나 경쟁률은 알 수 없어요. 지원자 수는 공개되지 않습니다.\n"
        "대신 이력서를 읽고 어느 공고가 요건에 가까운지는 골라 드릴 수 있어요."
    ),
    "회사 평판": (
        "회사 분위기나 평판은 저희가 가지고 있지 않아요. 채용공고에 적힌 것만 봅니다.\n"
        "직무·지역·경력으로 찾아 드리고, 고른 공고에 무엇이 적혀 있는지는 자세히 알려 드릴게요."
    ),
}

_UNAVAILABLE_NEXT = {
    "급여": ["서울 신입 공고 보여줘", "대기업 공고만"],
    "복지": ["재택 되는 공고", "정규직만"],
    "합격 가능성": ["내 이력서로 추천해줘", "신입도 되는 공고"],
    "회사 평판": ["대기업 공고만", "서울 공고 보여줘"],
}


def _to_chat_job(hit) -> schemas.JobChatJob:
    return schemas.JobChatJob(
        job_id=hit.job_id,
        company=hit.company,
        title=hit.title,
        source_url=hit.source_url,
        region=hit.region,
        career=hit.career_label,
        employment_type=hit.employment_type,
        deadline=hit.deadline,
        tech_stack=hit.tech_stack,
    )


_ORDINAL_PHRASE = re.compile(
    r"(?:\d+\s*번(?:째)?|첫\s*번째|두\s*번째|세\s*번째|네\s*번째|다섯\s*번째)"
    r"\s*(?:거|것|공고|건)?\s*(?:이랑|하고|과|와|은|는|이|가|을|를|의)?"
)


def _without_ordinal(message: str) -> str:
    """"2번 자세히 봐줘" 에서 자리를 가리키는 말을 뺀다.

    번호는 **서버가 이미 풀었다.** 그 말을 그대로 LLM에 넘기면, 공고 원문 하나만
    보고 있는 모델이 "2번"을 본문 속 항목 번호로 읽는다. 실제로 이렇게 답했다.

        이 공고에는 번호가 매겨진 항목이 없어 '2번'이 무엇을 뜻하는지 확인하기
        어렵습니다. 자세히 보고 싶은 항목을 말씀해 주세요.

    빼고 나서 남는 것이 없으면(그냥 "2번") 무엇을 묻는지 모르므로 공고 전체를
    설명해 달라고 바꾼다.
    """
    without = _ORDINAL_PHRASE.sub(" ", message)
    without = re.sub(r"\s+", " ", without).strip(" ,.·")
    return without or "이 공고가 어떤 일을 하는 자리인지 알려 주세요."


def _job_to_chat_job(job) -> schemas.JobChatJob:
    """저장소의 `Job`을 화면에 보여 줄 모양으로. `_to_chat_job`은 검색 결과용이라
    `career_label`을 이미 갖고 있지만, 저장소에서 바로 꺼낸 것은 그 값을 만들어야 한다."""
    return schemas.JobChatJob(
        job_id=job.job_id,
        company=job.company,
        title=job.title,
        source_url=job.source_url,
        region=job.region or "",
        career=store_search._career_label(job.career_type or "", job.min_career_years),
        employment_type=job.employment_type or "",
        deadline=job.deadline,
        tech_stack=list(job.tech_stack),
    )


def _job_text(job) -> str:
    """공고 한 건을 LLM이 읽을 글로. 본문은 자르지 않는다 — 요건은 대개 뒤쪽에 있다."""
    lines = [
        f"회사: {job.company}",
        f"제목: {job.title}",
        f"지역: {job.region or '미기재'}",
        f"경력: {store_search._career_label(job.career_type or '', job.min_career_years)}",
        f"학력: {job.education or '미기재'}",
        f"고용형태: {job.employment_type or '미기재'}",
        f"마감: {job.deadline or '미기재'}",
    ]
    if job.tech_stack:
        lines.append("기술 태그: " + ", ".join(job.tech_stack))
    if job.required_certifications:
        lines.append("자격증: " + ", ".join(job.required_certifications))
    lines.append("")
    lines.append(job.description or "(본문 없음)")
    return "\n".join(lines)


def _to_job_filters(filters: schemas.ChatFilters):
    return store_search.JobFilters(
        roles=filters.roles,
        skills=filters.skills,
        regions=filters.regions,
        career=filters.career,
        career_years=filters.career_years,
        employment_types=filters.employment_types,
        deadline_within_days=filters.deadline_within_days,
        keywords=filters.keywords,
        exclude_keywords=filters.exclude_keywords,
        posted_within_days=filters.posted_within_days,
    )


def _suggestions(filters, result) -> list[str]:
    """다음에 좁힐 거리. 사용자가 그대로 눌러 보낼 수 있는 말로 준다.

    이미 건 조건은 다시 권하지 않는다. 결과가 없으면 넓히는 쪽을 권한다.
    """
    if result.total == 0:
        wider = []
        if filters.regions:
            wider.append("지역 상관없이")
        if filters.career != "무관":
            wider.append("경력 상관없이")
        if filters.deadline_within_days:
            wider.append("마감 상관없이")
        if filters.posted_within_days is not None:
            wider.append("올라온 날 상관없이")
        if filters.exclude_keywords:
            wider.append(f"{filters.exclude_keywords[0]}도 포함해서")
        return wider[:3]

    narrower = []
    if not filters.regions:
        narrower.append("서울만")
    if filters.career == "무관":
        narrower.append("신입만")
    if not filters.deadline_within_days:
        narrower.append("마감 임박한 것만")
    if not filters.employment_types:
        narrower.append("정규직만")
    return narrower[:3]
