FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/cover_letter_rag:/app

RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 lms && useradd --uid 10001 --gid lms --create-home lms

COPY lms_api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY lms_api /app
# Django question sharing imports DB-free planning contracts from the AI source.
# Keep the sibling-source layout used by Django stores; copy pure contracts only.
COPY cover_letter_rag/app/__init__.py cover_letter_rag/app/models.py cover_letter_rag/app/job_requirements.py /app/cover_letter_rag/app/
COPY cover_letter_rag/app/application_planning/ /app/cover_letter_rag/app/application_planning/
COPY chatbot/cohort_document_rag.py chatbot/database.py /app/chatbot/
COPY vectordb/policy_ingestion.py vectordb/utills.py /app/vectordb/
RUN mkdir -p /app/media && chown lms:lms /app/media
USER 10001:10001
EXPOSE 8000

CMD ["gunicorn", "lms_server.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "180"]
