# Kisan Direct AI — backend + frontend in one image.
# Build from the REPO ROOT so the frontend files are in the build context:
#   docker build -f mvp/backend/Dockerfile -t kisan-direct-ai .
# (fly.toml and docker-compose.yml already use the repo root as context.)
# No .env file is ever copied into the image; secrets come from the
# platform (e.g. `fly secrets set`) at runtime.
FROM python:3.12.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KISAN_ENV=production \
    KISAN_SERVE_FRONTEND=1 \
    KISAN_DB_PATH=/data/kisan_direct.db

WORKDIR /app

# Non-root user. /data is the persistent-volume mount point on Fly.io;
# it is created here so the image also works without a volume attached.
RUN useradd -m -u 10001 appuser && mkdir -p /data && chown appuser:appuser /app /data

COPY mvp/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY mvp/backend/main.py ./main.py
COPY mvp/frontend/ ./frontend/
COPY standalone-pages/ ./standalone-pages/

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# Fly.io sets $PORT; default to 8000 when it is absent (local docker run).
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
