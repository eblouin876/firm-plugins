<!--
library: docker
versions-covered: "n/a"
last-verified: 2026-07-09
provenance: manual
sources: []
-->

# Containerization conventions (Docker / OCI)

Guidance for Dockerfiles, Compose, and image hygiene. Read after deciding to containerize. The project's existing setup overrides anything here.

## Contents
- Image principles
- Multi-stage builds
- Python (FastAPI / Django) images
- Node (React build) images
- Compose for local dev
- Image security & size
- Health & runtime

## Image principles
- **Pin base images** to a specific minor (e.g. `python:3.13-slim`, `node:22-slim`), not bare `latest` — reproducibility. Prefer slim/distroless over full where it works.
- **`.dockerignore`** is mandatory: exclude `.git`, `node_modules`, `__pycache__`, `.venv`, `.env`, build artifacts, tests, and local files. Keeps the build context small and avoids leaking secrets into images.
- **Layer for cache:** copy dependency manifests and install deps *before* copying app source, so code changes don't bust the dependency layer.
- **One concern per image:** the web app, a worker, and the database are separate containers — don't cram them together.

## Multi-stage builds
Use multi-stage builds to keep the final image small and free of build tooling:
- A `builder` stage installs build deps and compiles/installs; the final stage copies only the runtime artifacts.
- This is especially impactful for frontend (build with Node, serve static files from a tiny image) and for Python with compiled dependencies.

## Python (FastAPI / Django) images
- Install dependencies in a builder stage; copy the resulting environment/wheels into a slim runtime stage.
- Use a fast, reproducible install (e.g. `uv`, or `pip` with a lockfile/hashes). Copy the lockfile and install before copying source.
- Set `PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1`.
- Run via an ASGI server for FastAPI (`uvicorn`/`gunicorn` with uvicorn workers) or WSGI/ASGI for Django, bound to `0.0.0.0` and the platform's port.
- Migrations are NOT run in the image build — they're a deploy-time step (see deploy-operate.md).

## Node (React build) images
- Build stage: `npm ci` (clean, lockfile-faithful) then build.
- Final stage: serve the static bundle from a minimal web server (nginx/caddy) or hand the artifact to the platform's static hosting. Don't ship Node and dev dependencies to production for a static SPA.
- For an SSR/RSC framework (Next, React Router framework mode), the runtime stage runs the Node server with only production dependencies.

## Compose for local dev
- `docker-compose.yml` brings up the full local stack with one command: app + Postgres (+ Redis/worker as needed).
- Use named volumes for database data so it persists across restarts; bind-mount source for live reload in dev.
- Wire service-to-service via Compose network names (e.g. `db:5432`), env vars for config, and `depends_on` with healthchecks so the app waits for a ready database.
- Keep dev-only concerns (bind mounts, debug ports) out of the production image.

## Image security & size
- **Run as non-root:** create and switch to an unprivileged user; don't run the app as root.
- **Minimize surface:** slim/distroless base, only runtime deps in the final image, no shell tooling you don't need.
- **No secrets in images or layers:** never `COPY` a `.env` or bake credentials in. Secrets are injected at runtime. Remember deleted files persist in earlier layers.
- **Scan images** in CI (Trivy/Grype/Docker Scout) and keep base images patched — this is the build-time half of OWASP A03 (supply chain).

## Health & runtime
- Define a `HEALTHCHECK` (or platform health endpoint) so orchestrators know when the container is actually ready/alive.
- Handle termination signals gracefully (SIGTERM) so in-flight requests drain on shutdown/rollout.
- Set resource requests/limits at the orchestration layer to avoid noisy-neighbor problems.
- Log to stdout/stderr (12-factor) and let the platform collect — don't write logs to files inside the container.
