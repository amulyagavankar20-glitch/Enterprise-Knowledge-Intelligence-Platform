FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    DOCUMENT_STORAGE_DIR=/app/stored_documents \
    HF_HOME=/home/eki/.cache/huggingface

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin eki \
    && mkdir -p /app/stored_documents /home/eki/.cache/huggingface \
    && chown -R eki:eki /app /home/eki

COPY --chown=eki:eki backend/app ./backend/app
COPY --chown=eki:eki migrations ./migrations
COPY --chown=eki:eki alembic.ini ./alembic.ini
COPY --chown=eki:eki frontend/index.html frontend/app.css frontend/app.js ./frontend/

USER eki
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=120s \
  CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
