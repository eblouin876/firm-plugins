# Dev Dockerfile for this block (Stage 3 #26, Step 4). Boots the API for
# LOCAL DEVELOPMENT via docker-compose.yml (this directory) — not a
# hardened production image (no multi-arch build, no distroless final
# stage, no image signing); those are devops/infrastructure block concerns
# for whichever real deploy target a project picks (Stage 9+).
#
# Base image and uv version both per references/compatibility-matrix.md:
# "Containers" (python:3.13-slim-bookworm) and the uv pin CI already uses
# (0.11.31, "Security tooling" row) — one uv version across the whole kit,
# not a separately-drifting Docker-only pin.
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
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# `--no-dev`: this image boots the API (docker-compose's `api` service,
# possibly running `alembic upgrade head` first) — it never runs the test
# suite, so pytest/httpx/aiosqlite (the `dev` dependency-group in
# pyproject.toml) have no reason to be inside it. No `uv.lock` is
# committed to this repo (this block's own hermetic test suite pins via
# `uv run --with <pkg>==<pin>` instead — see README.md's "Testing"
# section) — `uv sync` here resolves and locks fresh inside THIS build
# layer, reproducible for this build, not frozen across rebuilds. A
# project that wants a byte-for-byte-frozen image commits its own
# `uv.lock` (`uv lock` from this directory) and swaps this to
# `uv sync --frozen --no-dev`.
RUN uv sync --no-dev

# Non-root: least privilege at runtime — an RCE in a dependency, or a
# container escape, doesn't get root inside this container either. Matches
# references/security/secure-baseline.md's "Least privilege" posture.
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app \
    && chown -R app:app /app /opt/venv
USER app

EXPOSE 8000

# `--reload` is deliberate: this is the DEV image (docker-compose.yml
# bind-mounts `./app` and `./alembic` over the copied-in source at
# runtime, so an edit on the host is picked up live). A production image
# built from this same Dockerfile for a real deploy target drops
# `--reload` and the compose bind mounts — out of scope for this dev seam
# (Stage 9's devops/infrastructure block owns that image).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
