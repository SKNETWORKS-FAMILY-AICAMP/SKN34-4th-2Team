FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 lms && useradd --uid 10001 --gid lms --create-home lms

COPY lms_api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY lms_api /app
COPY chatbot/cohort_document_rag.py chatbot/database.py /app/chatbot/
COPY vectordb/policy_ingestion.py vectordb/utills.py /app/vectordb/
RUN mkdir -p /app/media && chown lms:lms /app/media
USER 10001:10001
EXPOSE 8000

CMD ["gunicorn", "lms_server.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "180"]
