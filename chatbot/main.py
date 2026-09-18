"""LMS 학생 챗봇 단독 FastAPI 서버.

기본 개발 환경에서는 취업 코치 통합 서버에 포함되어 있으므로 이 파일을 따로 띄울 필요가 없다.

    python -m uvicorn app.integrated:app --app-dir cover_letter_rag --port 8000

챗봇만 따로 띄워 개발할 때만 사용한다.

    uvicorn chatbot.main:app --reload --port 8001

이 경우 Flutter는 --dart-define=STUDENT_CHATBOT_API_URL=http://127.0.0.1:8001 로 맞춘다.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chatbot.api import router

app = FastAPI(title="LMS 학생 챗봇 API", version="0.1.0")

origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOW_ORIGINS", "").split(",")
    if origin.strip()
]
origin_regex = os.environ.get("CORS_ALLOW_ORIGIN_REGEX", "").strip() or (
    r"http://(localhost|127\.0\.0\.1)(:\d+)?"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=origin_regex,
    allow_methods=["POST"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(router)
