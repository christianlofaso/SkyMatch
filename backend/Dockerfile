# SkyMatch backend image — shared by BOTH Railway services (web + worker); they run the
# same image with different start commands (web: uvicorn via railway.toml / Procfile `web`;
# worker: `python -m worker.ingest` via railway.worker.toml / Procfile `worker`).
#
# Build context is backend/ (set the Railway service "root directory" to backend/).
FROM python:3.12-slim

# - PYTHONUNBUFFERED: stream logs immediately (no buffering) so Railway shows them live.
# - PYTHONDONTWRITEBYTECODE: no .pyc clutter in the container.
# - PIP_NO_CACHE_DIR: smaller image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Install deps first (layer-cached unless requirements.txt changes). psycopg[binary] +
# the other deps ship wheels, so no system build toolchain is needed on slim. If a future
# dep needs to compile, add: RUN apt-get update && apt-get install -y --no-install-recommends gcc
COPY requirements.txt .
RUN pip install -r requirements.txt

# App code (.dockerignore keeps venv/.env/scratch/__pycache__ out).
COPY . .

# Run as a non-root user (defense in depth).
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Default = the WEB service. Bind the platform-injected $PORT (Railway sets it). The worker
# service overrides this command (see railway.worker.toml / Procfile). Shell form so $PORT expands.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
