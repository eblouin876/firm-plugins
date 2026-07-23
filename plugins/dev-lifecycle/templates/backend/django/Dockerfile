# Dev Dockerfile for this block (Stage 4 #27, Step 4). Boots the API for
# LOCAL DEVELOPMENT via docker-compose.yml (this directory) — not a
# hardened production image (no multi-arch build, no distroless final
# stage, no image signing); those are devops/infrastructure block concerns
# for whichever real deploy target a project picks (Stage 9+). Mirrors
# `backend/fastapi/Dockerfile`'s own posture line-for-line (same base
# image, same uv-via-COPY-from pattern, same non-root policy) — see that
# file's comments for the shared rationale not repeated here.
#
# Base image, uv version, and Postgres client tooling all per
# references/compatibility-matrix.md's "Containers" row (`python:3.13-
# slim-bookworm`, `ghcr.io/astral-sh/uv:0.11.31`) — the SAME pins
# `backend/fastapi/Dockerfile` uses, now cited for both blocks in that
# matrix row rather than re-pinned separately for this track.
FROM python:3.13-slim-bookworm

# uv via its own official, pinned distroless image (COPY --from, no pip-
# installing uv into the app's own venv) — the pattern
# https://docs.astral.sh/uv/guides/integration/docker/ documents.
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

# `--no-dev`: this image boots the API (docker-compose's `api` service,
# migrating then serving) — it never runs the test suite, so
# pytest/pytest-django/model-bakery (the `dev` dependency-group in
# pyproject.toml) have no reason to be inside it. No `uv.lock` is
# committed to this repo (same posture as `backend/fastapi`'s own
# Dockerfile — see that file's comment) — `uv sync` here resolves fresh
# inside THIS build layer. A project that wants a byte-for-byte-frozen
# image commits its own `uv.lock` (`uv lock` from this directory) and
# swaps this to `uv sync --frozen --no-dev`.
RUN uv sync --no-dev

# Non-root: least privilege at runtime — an RCE in a dependency, or a
# container escape, doesn't get root inside this container either. Matches
# references/security/secure-baseline.md's "Least privilege" posture, and
# `backend/fastapi/Dockerfile`'s identical policy for this track.
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app \
    && chown -R app:app /app /opt/venv
USER app

EXPOSE 8000

# `gunicorn` (WSGI), not `uvicorn` — this block's `config.wsgi:application`
# is the primary production entrypoint (`pyproject.toml`'s own comment: "
# gunicorn is the conventional WSGI-path production server"); `config.asgi:
# application` exists too (see that module) for a project that later adds
# real async/websocket views, at which point this CMD swaps to `uvicorn
# config.asgi:application --host 0.0.0.0 --port 8000 --reload`, mirroring
# `backend/fastapi/Dockerfile`'s own uvicorn CMD exactly. `--reload` is
# deliberate here too: this is the DEV image (docker-compose.yml
# bind-mounts `./core`/`./config` over the copied-in source at runtime, so
# an edit on the host is picked up live) — gunicorn's own `--reload` flag
# (documented, dev-oriented) restarts workers on a source change the same
# way uvicorn's does. A production image built from this same Dockerfile
# for a real deploy target drops `--reload` and the compose bind mounts —
# out of scope for this dev seam (Stage 9's devops/infrastructure block
# owns that image).
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--reload"]
