"""실험 전용 서버: python -m uvicorn chatbot_lab.main:app --port 8002."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chatbot_lab.api import flutter_router, router

app = FastAPI(title="LMS 학생 챗봇 Luna Lab", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(router)
app.include_router(flutter_router)
