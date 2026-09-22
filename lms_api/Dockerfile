FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY lms_api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY lms_api /app
EXPOSE 8000

CMD ["gunicorn", "lms_server.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
