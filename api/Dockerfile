# gRPC API image. Build context is the project root (see compose.yaml), so the
# COPY paths below are relative to the project root.
FROM python:3.12-slim

# Unbuffered stdout so `docker compose logs` shows prints immediately, and no
# .pyc files in the container.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Same uid/gid as the worker image: both must be able to write the shared /data
# volume, so the ids have to match.
ARG APP_UID=10001
ARG APP_GID=10001

WORKDIR /app

# Dependencies first (their own layer): a code change does not reinstall them,
# only a change to requirements-api.txt does.
COPY requirements-api.txt ./requirements-api.txt
RUN pip install --no-cache-dir -r requirements-api.txt

# Non-root user, and /data pre-created and owned by it. A fresh named volume
# mounted on /data inherits this ownership, so both services can write it.
RUN groupadd --gid ${APP_GID} app \
 && useradd --uid ${APP_UID} --gid ${APP_GID} --create-home \
            --shell /usr/sbin/nologin app \
 && mkdir -p /data \
 && chown -R app:app /data /app

# Code last: editing api/*.py only invalidates this small layer. The generated
# stubs ship with the code, so grpcio-tools is not needed in the image.
COPY --chown=app:app api ./api

# Drop privileges.
USER app

# gRPC port the server listens on (matches GRPC_PORT below).
EXPOSE 50051

CMD ["python", "-u", "api/server.py"]
