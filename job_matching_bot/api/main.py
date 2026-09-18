"""추천 API 서버.

    uvicorn job_matching_bot.api.main:app --reload --port 8010

앱은 이력서 평문과 희망 조건을 보내고, 서버는 추천 목록과 근거 문장을 돌려준다.
이력서는 저장하지 않는다. 임베딩해 검색에 쓰고 응답 후 버린다.

CORS는 개발용이다. 저장소 루트 `.env`의 두 값으로 켠다. 둘 다 비어 있으면 아무 출처도
허용하지 않으므로 배포본은 그대로 두면 된다.

    CORS_ALLOW_ORIGINS       정확히 일치하는 출처 목록(쉼표 구분)
    CORS_ALLOW_ORIGIN_REGEX  정규식. 개발 중에는 로컬호스트의 아무 포트나 허용한다

`flutter run -d chrome`은 실행할 때마다 포트가 달라진다. 포트를 고정하지 않아도 되게
`CORS_ALLOW_ORIGIN_REGEX = 'http://(localhost|127\.0\.0\.1)(:\d+)?'` 를 쓴다.
로컬호스트만 매칭하므로 외부 사이트는 여전히 막힌다.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from job_matching_bot.api import schemas
from job_matching_bot.api.ops_meta import (
    JOB_CHAT_PROMPT_VERSION,
    JOB_RECOMMEND_PROMPT_VERSION,
    openai_model,
    reasoning_effort,
)
from job_matching_bot.api.service import (
    ChatService,
    RecommendService,
    SearchUnavailable,
    StoreUnavailable,
)
from job_matching_bot.env import ensure_loaded
from job_matching_bot.retrieval.pinecone_index import client, index_name


def _with_recommend_ops(response: schemas.RecommendResponse) -> schemas.RecommendResponse:
    return response.model_copy(
        update={
            "prompt_version": JOB_RECOMMEND_PROMPT_VERSION,
            "model": openai_model(),
            "reasoning_effort": reasoning_effort(),
        }
    )


def _with_chat_ops(response: schemas.JobChatResponse) -> schemas.JobChatResponse:
    return response.model_copy(
        update={
            "prompt_version": JOB_CHAT_PROMPT_VERSION,
            "model": openai_model(),
            "reasoning_effort": reasoning_effort(),
        }
    )

@asynccontextmanager
async def _lifespan(_: FastAPI):
    """첫 요청이 물어야 할 준비 비용을 서버가 뜰 때 미리 치른다.

    임베딩 클라이언트를 처음 만드는 데 2.3초, Pinecone 인덱스를 처음 잡는 데 1.2초가
    든다. 그냥 두면 그 3.5초를 **처음 추천을 누른 사람**이 기다린다.

    실패해도 서버는 뜬다. 준비를 못 했을 뿐이고 요청이 오면 그때 다시 시도한다.
    """
    try:
        from langchain_openai import OpenAIEmbeddings

        from job_matching_bot.retrieval.pinecone_index import EMBEDDING_MODEL, index

        await asyncio.to_thread(
            OpenAIEmbeddings(model=EMBEDDING_MODEL).embed_query, "준비"
        )
        await asyncio.to_thread(index().describe_index_stats)
    except Exception as error:  # noqa: BLE001 — 준비 실패가 서버를 막을 이유는 없다
        print(f"[준비] 미리 데우지 못했습니다: {type(error).__name__}")
    yield


app = FastAPI(
    lifespan=_lifespan,
    title="AI 취업 코치 — 채용공고 추천 API",
    version="0.1.0",
    description="이력서를 읽고 채용공고를 추천한다. 벡터 검색 + LLM 재정렬 + 근거 검증.",
)

ensure_loaded()

_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOW_ORIGINS", "").split(",")
    if origin.strip()
]
_origin_regex = os.environ.get("CORS_ALLOW_ORIGIN_REGEX", "").strip() or None
if _origins or _origin_regex:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_origin_regex=_origin_regex,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

@app.middleware("http")
async def _log_duration(request, call_next):
    """요청마다 걸린 시간을 남긴다.

    앱은 90초를 기다리다 포기하는데, 그때 서버가 오래 걸린 것인지 아예 못 받은
    것인지 알 길이 없었다. 여기 한 줄이 남으면 다음에는 가려낼 수 있다.
    LLM이 느렸던 요청은 [느림] 으로 표시해 눈에 띄게 한다.
    """
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        print(f"[요청] {request.method} {request.url.path} 실패 "
              f"{time.perf_counter() - started:.1f}초")
        raise
    seconds = time.perf_counter() - started
    slow = " [느림]" if seconds >= 30 else ""
    print(f"[요청] {request.method} {request.url.path} "
          f"{response.status_code} {seconds:.1f}초{slow}")
    return response


_service = RecommendService()
_chat = ChatService()


@app.get("/health", response_model=schemas.HealthResponse)
def health() -> schemas.HealthResponse:
    try:
        stats = client().Index(index_name()).describe_index_stats()
        count = int(stats.get("total_vector_count", 0))
    except Exception:
        count = -1
    return schemas.HealthResponse(
        index_name=index_name(),
        vector_count=count,
        llm_configured=bool(os.environ.get("OPENAI_API_KEY")),
    )


@app.post("/api/v1/resume/profile", response_model=schemas.ResumeProfileOut)
def resume_profile(request: schemas.ProfileRequest) -> schemas.ResumeProfileOut:
    """이력서를 검색용으로 구조화한다. **저장할 때 미리 불러 두라고 낸 창구다.**

    추천이 이걸 다시 만들면 두 가지를 잃는다. 매번 2.7초를 기다리고, 검색어가 조금씩
    달라져 같은 이력서인데도 추천 목록이 흔들린다. 앱이 저장 시점에 한 번 받아 두었다가
    추천 요청에 `profile`로 실어 보내면 둘 다 사라진다.

    이력서를 고쳤으면 다시 부르면 된다. 안 보내면 서버가 그때 만든다.
    """
    warnings: list[str] = []
    profile = _service.build_profile(
        schemas.RecommendRequest(resume_text=request.resume_text), warnings
    )
    if warnings:
        raise HTTPException(status_code=503, detail=warnings[0])
    return profile


@app.post("/api/v1/jobs/recommend", response_model=schemas.RecommendResponse)
def recommend(request: schemas.RecommendRequest) -> schemas.RecommendResponse:
    try:
        return _with_recommend_ops(_service.recommend(request))
    except SearchUnavailable as error:
        # 검색이나 조건 판정이 실패하면 추천하지 않는다. 근거 없는 목록을 보여 주지 않는다.
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/v1/jobs/recommend/stream")
async def recommend_stream(request: schemas.RecommendRequest) -> StreamingResponse:
    """추천을 하면서 단계를 흘려보낸다. 마지막 줄에 결과가 온다.

    추천은 15초쯤 걸린다. 한 번에 돌려주면 앱은 그동안 무엇이 진행 중인지 알 수 없어
    막대만 돌린다. 여기서는 단계가 바뀔 때마다 한 줄씩 내보낸다.

    형식은 Server-Sent Events다. 줄마다 `data: {json}` 이고 이벤트는 셋이다.

        {"event": "progress", "stage": "search", "detail": null}   단계 시작
        {"event": "progress", "stage": "search", "detail": "..."}  단계 끝, 결과 한 줄
        {"event": "done", "result": {...}}                         추천 결과 (기존 응답 그대로)
        {"event": "error", "detail": "..."}                        실패

    추천 자체는 동기 코드라 스레드에서 돌리고, 알림은 큐로 받아 넘긴다. 앱이 이 경로를
    모르거나 실패하면 기존 `/api/v1/jobs/recommend`로 물러나면 된다 — 그쪽은 그대로다.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def push(payload: dict | None) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, payload)

    def progress(stage: str, detail: str | None) -> None:
        push({"event": "progress", "stage": stage, "detail": detail})

    def work() -> None:
        try:
            result = _with_recommend_ops(
                _service.recommend(request, progress=progress)
            )
            push({"event": "done", "result": result.model_dump(mode="json")})
        except SearchUnavailable as error:
            push({"event": "error", "detail": str(error)})
        except Exception as error:  # noqa: BLE001 — 끊긴 응답보다 이유 한 줄이 낫다
            push({"event": "error", "detail": f"추천에 실패했습니다: {type(error).__name__}"})
        finally:
            push(None)

    async def stream():
        threading.Thread(target=work, daemon=True).start()
        while True:
            payload = await queue.get()
            if payload is None:
                return
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        # 프록시가 모아 두었다가 한꺼번에 보내면 단계 표시가 의미를 잃는다.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/v1/jobs/chat", response_model=schemas.JobChatResponse)
def chat(request: schemas.JobChatRequest) -> schemas.JobChatResponse:
    """말로 공고를 찾는다. 앱은 직전 응답의 `filters`를 그대로 실어 보내 대화를 잇는다."""
    try:
        return _with_chat_ops(_chat.chat(request))
    except StoreUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
