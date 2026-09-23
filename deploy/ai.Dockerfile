# 취업 코치 AI 서버 — 챗봇 · 공부방 노트 · 이력서 첨삭 · 공고 추천을 한 프로세스로 띄운다.
#
#   cover_letter_rag/app/integrated.py 가 넷을 한 앱에 붙인다:
#     /api/v1/student-chatbot/*  학생 챗봇
#     /api/v1/study-notes/*      공부방 노트
#     /resume-review/*           이력서 첨삭
#     /api/v1/jobs/*             공고 추천
#
# LMS(Django)는 이 서버를 CHATBOT_URL · JOBS_URL 로 부른다. 상자를 나눠 두는 이유는
# 무거운 AI 의존성(openai · pinecone · langchain)을 Django 이미지에 섞지 않고, AI 가 죽어도
# LMS 는 살아 있게 하기 위해서다.
#
# 만들기(저장소 루트에서):
#   docker build -f deploy/ai.Dockerfile -t lms-ai .

# 복습 문제 검증기 — 학생 브라우저와 같은 Pyodide 로 문제를 돌려 본다(study_notes/practice/runner.py)
FROM node:20-slim AS verifier
WORKDIR /verifier
COPY practice_verifier/package.json practice_verifier/package-lock.json ./
RUN npm ci --omit=dev
COPY practice_verifier/ ./

FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app

# 공부방 노트 · 복습 문제가 수업 저장소를 git 으로 읽는다. 비공개 저장소는 환경변수 GITHUB_TOKEN
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# 검증기를 돌릴 node — 같은 데비안(bookworm)이라 바이너리만 옮겨도 돈다
COPY --from=verifier /usr/local/bin/node /usr/local/bin/node
COPY --from=verifier /verifier /app/practice_verifier

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 통합 서버가 부르는 네 묶음만 담는다
COPY cover_letter_rag /app/cover_letter_rag
COPY job_matching_bot /app/job_matching_bot
COPY chatbot /app/chatbot
COPY study_notes /app/study_notes
# 챗봇이 정책 문서 색인을 여기서 읽는다(chatbot/student_chatbot.py → vectordb)
COPY vectordb /app/vectordb
# 공고 저장소가 `jobs` 스키마를 확인할 때 읽는다(job_matching_bot/ingestion/sqlite_store.py)
COPY scripts/firestore_to_postgres/jobs_schema.sql /app/scripts/firestore_to_postgres/jobs_schema.sql

EXPOSE 8000

# --app-dir 로 cover_letter_rag 를 얹어야 `app.integrated` 가 풀린다(로컬 실행과 같다)
CMD ["python", "-m", "uvicorn", "app.integrated:app", "--app-dir", "cover_letter_rag", \
     "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "120"]
