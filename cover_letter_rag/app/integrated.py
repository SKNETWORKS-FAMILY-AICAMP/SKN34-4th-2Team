"""Run from repo root: python -m uvicorn app.integrated:app --app-dir cover_letter_rag.

학생 LMS 챗봇(chatbot/)과 공부방 노트(study_notes/)도 이 통합 서버에 포함된다.
로컬 개발은 8000 포트 하나만 띄우면 된다.
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chatbot.api import router as student_chatbot_router
from study_notes.api import router as study_notes_router
from job_matching_bot.api.main import app as matching_app
from app.main import app as review_app
from app.trace_privacy import enable_trace_privacy

# 위 앱들을 불러오며 .env 가 환경변수로 들어왔다. 첫 LLM 호출보다 먼저 추적의 개인정보 가리기를 건다
enable_trace_privacy()

app = FastAPI(title='LMS 취업 코치 통합 API', docs_url=None, redoc_url=None, openapi_url=None)
origins = [s.strip() for s in os.environ.get('CORS_ALLOW_ORIGINS', '').split(',') if s.strip()]
regex = os.environ.get('CORS_ALLOW_ORIGIN_REGEX', '').strip() or None
if origins or regex:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_origin_regex=regex,
                       allow_methods=['GET', 'POST', 'PUT', 'DELETE'],
                       allow_headers=['Content-Type', 'Authorization'])

# 학생 챗봇·공부방은 APIRouter라 mount가 아니라 include_router로 붙인다.
# mount('/')보다 먼저 등록해야 /api/v1/student-chatbot/*, /api/v1/study-notes/* 가
# matching_app에 가려지지 않는다.
app.include_router(student_chatbot_router)
app.include_router(study_notes_router)

# Both apps already own /api/v1/jobs/recommend with incompatible schemas.
# Preserve matching's root routes and isolate the legacy review app by prefix.
app.mount('/resume-review', review_app)
app.mount('/', matching_app)
