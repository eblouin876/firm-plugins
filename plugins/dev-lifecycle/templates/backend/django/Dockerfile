# Multi-stage image for this block — mirrors `backend/fastapi/Dockerfile`'s
# posture line-for-line (same base image, uv-via-COPY pattern, non-root uid
# 1000, `dev` + hardened `prod` stages with `prod` last/default). See that
# file's comments for the shared rationale not repeated here.
#
# - `dev`   — live-reload for `just dev` (docker-compose.yml sets `target: dev`).
# - `prod`  — hardened, LAST/default stage: a `docker build` with no
#             `--target` (security-gate containers job + the infra block's ECR
#             image) builds this; no ARG/ENV secret ever, non-root, no --reload,
#             HEALTHCHECK on readiness.
#
# Base image + uv version per references/compatibility-matrix.md "Containers"
# (python:3.13-slim-bookworm, ghcr.io/astral-sh/uv:0.11.31).

FROM python:3.13-slim-bookworm AS base

COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY manage.py ./
COPY config ./config
COPY core ./core

# `--no-dev`: boots the API, never runs the test suite. Same no-committed-lock
# posture as backend/fastapi's Dockerfile.
RUN uv sync --no-dev

# Non-root (uid/gid 1000 — matches the infra block's ECS task def
# `user = "1000:1000"`).
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --home-dir /app --no-create-home app \
    && chown -R app:app /app /opt/venv
USER app

EXPOSE 8000

# --- dev: live-reload (docker-compose sets target: dev) ---------------------
FROM base AS dev

# gunicorn's own `--reload` (documented, dev-oriented) restarts workers on a
# source change, the same way uvicorn's does; docker-compose bind-mounts
# `./core`/`./config` over the copied-in source.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--reload"]

# --- prod: hardened, default/final stage ------------------------------------
FROM base AS prod

# stdlib-only container HEALTHCHECK on readiness (no curl/wget in the slim
# image). The infra block's ALB uses its own target-group check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/readyz', timeout=3).status == 200 else 1)"]

# `gunicorn` (WSGI) is the production entrypoint; `config.asgi:application`
# exists for a project that later adds async/websocket views (swap to
# `uvicorn config.asgi:application`). NO `--reload`; migrations run as a
# separate deploy step (the infra block's deploy runbook).
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
