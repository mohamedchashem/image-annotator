# Web UI image: the FastAPI backend (a gRPC client of api/) plus the static
# page. Build context is the project root (see compose.yaml), so the COPY paths
# below are relative to the project root.
FROM python:3.12-slim

# Unbuffered stdout so `docker compose logs` shows the request lines immediately,
# and no .pyc files in the container.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Same uid/gid as the api and worker images, so the /app files are owned by the
# same unprivileged user everywhere.
ARG APP_UID=10001
ARG APP_GID=10001

WORKDIR /app

# Dependencies first (their own layer): a code change does not reinstall them,
# only a change to ui/requirements.txt does. Pillow/pika are NOT installed here:
# this process never touches images or RabbitMQ, it only speaks gRPC.
COPY ui/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Non-root user, owner of /app.
RUN groupadd --gid ${APP_GID} app \
 && useradd --uid ${APP_UID} --gid ${APP_GID} --create-home \
            --shell /usr/sbin/nologin app \
 && chown -R app:app /app

# The generated stubs are reused as-is (never edited, never regenerated in the
# image), so only these two files are needed from api/. They land in /app/api,
# which is what ui/app.py puts on sys.path.
COPY --chown=app:app api/annotator_pb2.py api/annotator_pb2_grpc.py ./api/

# Code last: editing the app or the page only invalidates these layers.
COPY --chown=app:app ui/app.py ./ui/app.py
COPY --chown=app:app ui/static ./ui/static

# Drop privileges.
USER app

# HTTP port the page is served on (compose publishes it on the host).
EXPOSE 8000

# --no-access-log: the app writes exactly one log line per request itself.
CMD ["python", "-u", "-m", "uvicorn", "ui.app:app", \
     "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
