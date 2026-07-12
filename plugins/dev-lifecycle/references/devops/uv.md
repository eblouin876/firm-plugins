<!--
library: uv
versions-covered: "uv 0.x"   # verified current: 0.11.28 (2026-07-07)
last-verified: 2026-07-12
provenance: auto-generated (pending review)
sources:
  - https://docs.astral.sh/uv/
  - https://docs.astral.sh/uv/concepts/projects/dependencies/
  - https://docs.astral.sh/uv/guides/integration/docker/
  - https://github.com/astral-sh/uv/releases
  - https://pypi.org/pypi/uv/json
-->

# uv conventions

Conventions for uv, Astral's Rust-based Python package/project manager and the firm's emerging Python standard. Load when you detect a `uv.lock`, a `[tool.uv]` or `[dependency-groups]` table in `pyproject.toml`, a `.python-version`, or a `uv` invocation in CI/Dockerfile. The project's own conventions override anything here.

## Contents
- Version check (do this first)
- Project model
- Adding & removing dependencies
- Dependency groups vs extras
- Running commands
- Locking & reproducibility
- Python version management
- The `uv pip` compat interface
- Docker
- CI
- Building & publishing
- Pitfalls

## Version check (do this first)
uv is pre-1.0 and ships often (current: **0.11.28**). The CLI surface and `uv.lock` schema are versioned and still move, so **pin uv for reproducibility** — don't float `latest`. Check with `uv self version` (uv's own version; `uv version` reports/sets the *project* version). In CI pin via `astral-sh/setup-uv` `version:`; in Docker pin the `COPY --from=ghcr.io/astral-sh/uv:0.11.28` tag or the installer version. The lockfile records its own `version`; a newer uv may rewrite it, so keep local and CI uv in step.

## Project model
Two files, **both committed**: `pyproject.toml` (declared deps, human-edited only in the `[project]`/`[dependency-groups]` sense) and `uv.lock` (fully resolved, cross-platform, **machine-owned — never hand-edit**). `uv sync` reconciles `.venv` to the lock (creating `.venv` and the interpreter as needed). `.venv` is disposable and git-ignored — never commit it.

## Adding & removing dependencies
Use `uv add <pkg>` / `uv remove <pkg>`: they edit `pyproject.toml`, re-resolve, update `uv.lock`, and sync `.venv` in one step. `uv add --dev <pkg>` targets the default `dev` group; `uv add --group <name> <pkg>` targets another group. Anti-pattern: hand-editing `[project.dependencies]` and forgetting to relock — that leaves lock/manifest out of sync. If you must edit by hand, follow with `uv lock`.

## Dependency groups vs extras
- **`[dependency-groups]`** (PEP 735) — local/dev-only deps (test, lint, docs). Not published to PyPI, not installed by consumers. Select with `--group <name>`, `--all-groups`, `--only-group <name>`. `dev` is the special default group (`--dev`/`--no-dev`/`--only-dev`), included by `uv sync`/`uv run` automatically. This is the firm default for tooling deps (TeamForge's model).
- **`[project.optional-dependencies]`** (extras) — optional *features* shipped to consumers, installed via `pip install pkg[extra]`. Select with `--extra <name>`/`--all-extras`. Use only for genuinely publishable optional features (grain-brain's `[project.optional-dependencies]` predates the group split — new dev tooling should go in `[dependency-groups]`).

## Running commands
`uv run <cmd>` executes in the synced env — it **replaces `source .venv/bin/activate` + `python`**. It auto-syncs first (lock + `.venv` are made current), so `uv run pytest`, `uv run python -m app`, `uv run ruff check` always run against the resolved env. Anti-pattern: activating the venv and calling bare `python`/`pip` — bypasses uv's sync guarantees.

## Locking & reproducibility
`uv lock` re-resolves without touching `.venv`; `uv lock --upgrade` bumps within constraints. In CI/containers, sync against the committed lock and fail on drift:
- `uv sync --locked` — assert the lock is up to date; **error** if `pyproject.toml` would change it (use in CI gates).
- `uv sync --frozen` — install strictly from the lock, don't even check or update it (fast, hermetic builds).
- `--no-dev` (or `--no-default-groups`) for production — omit dev-group deps.

## Python version management
uv manages interpreters itself: `uv python install 3.13`, `uv python list`, `uv python pin 3.13` (writes `.python-version`). `requires-python` in `pyproject.toml` bounds the resolution; `.python-version` selects the concrete interpreter for `.venv`. Commit `.python-version` for a consistent team/CI interpreter.

## The `uv pip` compat interface
`uv pip install`/`uv pip compile`/`uv pip sync` are a fast drop-in for pip/pip-tools against `requirements.txt` — for legacy repos or non-project scripts. In a real uv project prefer `uv add`/`uv sync`; don't mix `uv pip install` into a lockfile-managed `.venv` (it desyncs the lock).

## Docker
Pin uv by copying from the Astral image: `COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/`. Set `ENV UV_COMPILE_BYTECODE=1` (compile `.pyc` at build for faster cold start) and `ENV UV_LINK_MODE=copy` (avoid cross-filesystem symlink warnings with cache mounts). Install deps before source for layer caching, using a cache mount:
```dockerfile
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
```
Multi-stage: build `.venv` in a builder, then `COPY --from=builder /app/.venv /app/.venv` into a slim runtime and put `.venv/bin` on `PATH` — no uv needed at runtime. See containers.md.

## CI
Install uv via `astral-sh/setup-uv` with a pinned `version:` and `enable-cache: true`, or the install script. Run `uv sync --locked` (or `--frozen`) so a stale/uncommitted lock fails the build, then `uv run` the tests/linters. See cicd.md.

## Building & publishing
`uv build` produces sdist+wheel in `dist/` (both firm repos use the hatchling backend). `uv publish` uploads (trusted publishing / token). These are lockfile-independent — the lock governs the dev env, not the built artifact's metadata.

## Pitfalls
- Committing `.venv` — it's disposable; git-ignore it.
- Forgetting to commit `uv.lock`, or committing a lock that drifted from `pyproject.toml` (`uv sync --locked` in CI catches this).
- Hand-editing `uv.lock`.
- `pip install`-ing into a uv-managed `.venv` — desyncs the lock; use `uv add`.
- Floating uv version across dev/CI/Docker — pin it everywhere.
