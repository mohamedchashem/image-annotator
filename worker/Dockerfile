# YOLO worker image. Build context is the project root (see compose.yaml), so
# the COPY paths below are relative to the project root.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System libraries that opencv-python (libGL / libglib) and torch (libgomp)
# need and that python:3.12-slim (Debian trixie) does not ship. The glib package
# is called libglib2.0-0t64 there (the t64 time_t transition), not libglib2.0-0.
# --no-install-recommends keeps the image small; the apt lists go in this layer.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0t64 \
        libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# Same uid/gid as the api image so both can write the shared /data volume.
ARG APP_UID=10001
ARG APP_GID=10001

WORKDIR /app

# Dependencies first (their own layer). requirements-worker.txt pins the
# CPU-only PyTorch wheels from https://download.pytorch.org/whl/cpu, so this is
# the big, slow, but cached layer.
COPY requirements-worker.txt ./requirements-worker.txt
RUN pip install --no-cache-dir -r requirements-worker.txt

# Non-root user, and /data pre-created and owned by it (see api/Dockerfile).
RUN groupadd --gid ${APP_GID} app \
 && useradd --uid ${APP_UID} --gid ${APP_GID} --create-home \
            --shell /usr/sbin/nologin app \
 && mkdir -p /data \
 && chown -R app:app /data /app

# Weights are baked into the image: detector.py loads <project root>/yolov8n.pt,
# so keeping it at /app/yolov8n.pt means nothing is downloaded at runtime.
COPY --chown=app:app yolov8n.pt ./yolov8n.pt

# Code last: editing worker/*.py only invalidates this small layer.
COPY --chown=app:app worker ./worker

USER app

CMD ["python", "-u", "worker/worker.py"]
