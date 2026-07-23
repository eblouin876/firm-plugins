# Multi-stage image for this block.
#
# - `dev`   — live-reload for `just dev` (docker-compose.yml sets
#             `target: dev`, bind-mounts source, and overrides the command).
# - `prod`  — the hardened production image, and the LAST/default stage: a
#             `docker build` with no `--target` (the security-gate containers
#             job, and the infra block's ECR image build) builds this stage,
#             so what ships and what trivy scans is always the hardened one.
#
# Base image and uv version both per references/compatibility-matrix.md:
# "Containers" (python:3.13-slim-bookworm) and the uv pin CI already uses
# (0.11.31, "Security tooling" row) — one uv version across the whole kit.
# No ARG/ENV ever carries a secret: secrets are injected at RUNTIME (the
# infra block's ECS task `secrets`/`valueFrom`, or docker-compose env), never
# baked into an image layer (references/security/secure-baseline.md).

FROM python:3.13-slim-bookworm AS base

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

# `--no-dev`: this image boots the API — it never runs the test suite, so the
# `dev` dependency-group (pytest/httpx/aiosqlite) has no reason to be inside
# it. No `uv.lock` is committed here (this block's hermetic suite pins via
# `uv run --with`); `uv sync` resolves and locks fresh in THIS build layer. A
# project wanting a byte-for-byte-frozen image commits its own `uv.lock` and
# swaps this to `uv sync --frozen --no-dev`.
RUN uv sync --no-dev

# Non-root (uid/gid 1000 — matches the infra block's ECS task def
# `user = "1000:1000"`): least privilege at runtime, so an RCE in a dependency
# or a container escape doesn't land as root. References/security/
# secure-baseline.md's "Non-root containers".
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --home-dir /app --no-create-home app \
    && chown -R app:app /app /opt/venv
USER app

EXPOSE 8000

# --- dev: live-reload (docker-compose sets target: dev) ---------------------
FROM base AS dev

# `--reload` for local development: docker-compose.yml bind-mounts `./app` and
# `./alembic` over the copied-in source, so a host edit is picked up live.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- prod: hardened, default/final stage ------------------------------------
FROM base AS prod

# Liveness/readiness for orchestrators that honor a container HEALTHCHECK
# (the infra block's ALB uses its own target-group check on /readyz instead).
# stdlib only — python:3.13-slim-bookworm ships no curl/wget.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/readyz', timeout=3).status == 200 else 1)"]

# NO `--reload` in production. Migrations run as a separate deploy step
# (the infra block's deploy runbook), not baked into this CMD.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
