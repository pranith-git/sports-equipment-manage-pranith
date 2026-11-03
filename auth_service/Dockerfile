FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AUTH_DATABASE_PATH=/data/auth.db \
    LEGACY_DATABASE_PATH=/app/basedata.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && mkdir -p /data

COPY auth_service/*.py ./auth_service/
COPY basedata.db ./basedata.db
COPY auth_service/auth.db /data/auth.db

CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--access-logfile", "-", "--error-logfile", "-", "auth_service.app:app"]
