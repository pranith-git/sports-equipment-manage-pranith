FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INVENTORY_DATABASE_PATH=/data/inventory.db \
    LEGACY_DATABASE_PATH=/app/basedata.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && mkdir -p /data

COPY inventory_service/*.py ./inventory_service/
COPY seed_data.py ./seed_data.py
COPY basedata.db ./basedata.db
COPY inventory_service/inventory.db /data/inventory.db

CMD ["gunicorn", "--bind", "0.0.0.0:5002", "--access-logfile", "-", "--error-logfile", "-", "inventory_service.app:app"]
