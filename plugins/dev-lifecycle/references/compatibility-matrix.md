<!--
scope: cross-stack starter kit
versions-covered: "Stage 0 kit-wide pin set, 2026-07; Stage 2 security-tooling pin set, 2026-07; Stage 4 psycopg row, 2026-07; Stage 4 Step 3 django-cors-headers row, 2026-07; Stage 4 Step 4 Containers rows now also cite backend/django, 2026-07"
last-verified: 2026-07-23
provenance: manual
sources:
  - https://pypi.org/project/fastapi/
  - https://pypi.org/project/pydantic/
  - https://pypi.org/project/pydantic-settings/
  - https://pypi.org/project/asyncpg/
  - https://pypi.org/project/uvicorn/
  - https://www.sqlalchemy.org/blog/2026/04/16/sqlalchemy-2.1.0b2-released/
  - https://alembic.sqlalchemy.org/en/latest/changelog.html
  - https://www.djangoproject.com/download/
  - https://www.django-rest-framework.org/community/release-notes/
  - https://drf-spectacular.readthedocs.io/
  - https://pypi.org/project/psycopg/
  - https://pypi.org/project/django-cors-headers/
  - https://docs.djangoproject.com/en/5.2/releases/5.2/
  - https://nodejs.org/en/about/previous-releases
  - https://www.npmjs.com/package/pnpm?activeTab=versions
  - https://devblogs.microsoft.com/typescript/
  - https://react.dev/versions
  - https://vite.dev/blog/announcing-vite8
  - https://nextjs.org/docs/app/guides/upgrading/version-16
  - https://expo.dev/changelog/sdk-57
  - https://www.postgresql.org/about/news/postgresql-184-1710-1614-1518-and-1423-released-3297/
  - https://github.com/hashicorp/terraform/releases
  - https://registry.terraform.io/providers/hashicorp/aws/latest
  - https://hub.docker.com/_/python
  - https://hub.docker.com/_/node
  - https://www.npmjs.com/package/orval
  - https://www.npmjs.com/package/@tanstack/react-query
  - https://www.npmjs.com/package/eslint
  - https://www.npmjs.com/package/typescript-eslint
  - https://www.npmjs.com/package/prettier
  - https://pypi.org/project/bandit/
  - https://pypi.org/project/semgrep/
  - https://pypi.org/project/pip-audit/
  - https://pypi.org/project/uv/
  - https://docs.astral.sh/uv/concepts/projects/export/ (CLI flags cross-checked against `uv export --help`, uv 0.8.17)
  - https://pypi.org/project/checkov/
  - https://github.com/gitleaks/gitleaks/releases
  - https://github.com/aquasecurity/trivy/releases
  - https://github.com/aquasecurity/trivy/blob/main/contrib/install.sh
  - https://github.com/pypa/gh-action-pip-audit/tags
  - https://www.env0.com/blog/best-iac-scan-tool-comparing-checkov-vs-tfsec-vs-terrascan
-->

# Compatibility matrix

**The keystone reference.** A pinned, known-good version SET spanning the whole starter kit. Every template block and catalog component pins to this matrix — a block does not choose its own version of a kit-wide dependency. When a block's `versions-pinned-to` and this matrix disagree, this matrix wins; update the block. Cross-links `references/security/secure-baseline.md` for the security posture these pins are expected to run under.

## Contents
- Version check (do this first)
- Backend — Python
- Backend — Django track
- Frontend / web
- Client codegen
- Mobile
- Kit-wide lint & format tooling
- Data
- Infra
- Containers
- Security tooling (CI scanners)

## Version check (do this first)
Re-verify against official release notes/registries before bumping any line — recall is not a source. Three lines are deliberately held back from the newest available release; see the judgment calls inline. Re-run this check at least once a quarter or when a new template block is authored, whichever is sooner.

## Backend — Python
| Dep | Pinned line | Why this line |
| --- | --- | --- |
| Python | **3.13.x** | Latest stable with a mature C-extension/wheel ecosystem; 3.14 (released Oct 2025) is current but young for some third-party wheels — reassess next quarter. |
| FastAPI | **0.139.x** | Latest release line (0.139.2, Jul 2026); still pre-1.0, so pin the minor, not just the major. |
| Pydantic | **v2, 2.13.x** | Pydantic v2 only — v1 is a different library. 2.13.x is current stable; a 2.14 alpha exists but isn't GA. |
| pydantic-settings | **2.14.x** (2.14.2) | Current stable (PyPI, Jun 19 2026); `BaseSettings` was split out of Pydantic core at v2 (see `references/backend/pydantic.md`'s "Settings & secrets"). Requires `pydantic>=2.7.0` — compatible with this matrix's Pydantic 2.13.x pin above; the two version lines float independently. Used by `templates/components/backend/settings/`. |
| SQLAlchemy | **2.0.x** (2.0.51) | The 2.0 style (`Mapped[]`, `select()`) is the baseline every block writes to. 2.1 is beta-only (`0b2`) as of this pin — do not adopt pre-GA. |
| Alembic | **1.18.x** | Tracks SQLAlchemy 2.0; current stable. |
| asyncpg | **0.31.x** (0.31.0) | Current stable (PyPI, Nov 24 2025). The async PostgreSQL driver `db-session/`'s `configure_engine()` expects behind a `postgresql+asyncpg://` DATABASE_URL — see that component's fail-fast scheme guard. Added by Stage 3 Step 2 (#26), which is the first block to actually need a real async DB driver rather than just the ORM layer. |
| uvicorn | **0.51.x**, `uvicorn[standard]` extra | Current stable (PyPI, Jul 8 2026). ASGI server this block's `app.main:app` runs under; the `standard` extra pulls in `uvloop`/`httptools` for production-grade performance. Added by Stage 3 Step 2 (#26) alongside asyncpg, for the same reason. |
| PyJWT | **2.13.x** (2.13.0) | Current stable (PyPI). HS256 JWT signing/verification for `templates/components/security/auth/_core.py`'s `TokenService` — access/refresh token issuance and decode, algorithm pinned explicitly to HS256 at every `jwt.decode()` call (never inferred from the token's own header — see that module's own docstring). First consumed by backend/fastapi's Stage 5a (#41) auth wiring; the Django track consumes the identical pin once it vendors the same auth component in Stage 5b (#44) — this is a framework-neutral runtime dependency of the component itself, not FastAPI-specific. |
| argon2-cffi | **25.1.x** (25.1.0) | Current stable (PyPI). Argon2id password hashing for `templates/components/security/auth/_core.py`'s `PasswordService` — the OWASP-recommended default for new applications (see that class's own docstring on why Argon2id specifically, not Argon2i/Argon2d). Same "first consumed by FastAPI's Stage 5a, Django picks up the identical pin at Stage 5b (#44)" note as PyJWT above applies here too. |

## Backend — Django track
| Dep | Pinned line | Why this line |
| --- | --- | --- |
| Django | **5.2 LTS** | LTS branch, supported through Apr 2028 — the right default for a starter kit over a non-LTS feature release. |
| Django REST Framework | **3.17.x** | Current stable, tracks Django 5.2. |
| drf-spectacular | **0.30.x** | OpenAPI 3 schema generation for DRF; current stable, keep in lockstep with DRF. |
| psycopg | **3.3.x** (3.3.4), `[binary]` extra | Postgres driver for the Django track. Current stable (PyPI, verified for Stage 4 #27); Django 5.2's `django.db.backends.postgresql` engine auto-detects psycopg2 or psycopg (v3) and Django 5.2 prefers psycopg 3 — see Django 5.2 release notes' "Database backend API" note. The `[binary]` extra ships a self-contained wheel with no local libpq headers/C toolchain needed to install, matching this kit's "no surprise system deps" posture for `uv sync`. Added by Stage 4 Step 1 (#27), the first block on this track to need a real Postgres driver. |
| django-cors-headers | **4.9.x** (4.9.0) | Current stable (PyPI, released Sep 18 2025 — verified via `pypi.org/pypi/django-cors-headers/json`, `info.version`). The Django-ecosystem convention for CORS; `core/security/cors_lockdown/django.py` (Stage 4 Step 3, #27) emits this package's settings from `CORSPolicy` but never imports it directly — the Django block itself installs it and puts `"corsheaders"` in `INSTALLED_APPS` + `corsheaders.middleware.CorsMiddleware` in `MIDDLEWARE`. Supports Django 4.2–6.0 per its own PyPI classifiers, comfortably covering this matrix's Django 5.2 LTS pin above. |

## Frontend / web
| Dep | Pinned line | Why this line |
| --- | --- | --- |
| Node.js | **24.x LTS** ("Krypton") | Active LTS as of this pin. Node 26 exists as Current but does not enter LTS until Oct 2026 — don't build the kit's baseline on it yet. |
| pnpm | **11.x** | Current stable major (dist-tag `latest`); newer store format and native registry commands. |
| TypeScript | **6.0** | TS 7.0 (Go-native compiler, ~10x faster) shipped Jul 9 2026 — 12 days before this pin. Held back one release deliberately: editor/lint-plugin ecosystem is still catching up to the native port. Revisit next quarter. |
| React | **19.x** (19.2.x) | Current stable major; Actions/`use()` are the baseline idiom set. |
| Vite | **8.x** (8.1.x) | Default bundler is now Rolldown (Rust) — faster cold start/HMR than Vite 7's Rollup default. |
| Next.js (App Router) | **16.x** (16.2.x) | App Router is the only sensible default at this line (Pages Router is maintenance-mode); Turbopack is the default bundler for `dev` and `build`. |

## Client codegen
| Dep | Pinned line | Why this line |
| --- | --- | --- |
| orval | **8.22.x** (8.22.0) | Current stable (Jul 14 2026). Generates the shared `packages/api-client` from the backend's OpenAPI schema — React Query hooks over a custom `fetch` mutator, no axios (gate-1 locked choice). |
| @tanstack/react-query | **5.101.x** (5.101.3) | Current v5 line. **Judgment call:** the true latest patch at verification time, 5.101.4, falls inside the workspace's configured `minimumReleaseAge` supply-chain window (`templates/monorepo/pnpm-workspace.yaml`; packages newer than that window are rejected by pnpm's install-time check unless explicitly excluded) — 5.101.3 (older) clears it, so pin that instead of fighting the gate with a per-version exclusion that goes stale on the next bump. Re-check next quarter; by then 5.101.4+ will have aged out of the window on its own. |

## Mobile
| Dep | Pinned line | Why this line |
| --- | --- | --- |
| Expo SDK | **57** | Current stable (released Jun 30 2026), ships React Native 0.86 as a small, non-breaking upgrade over SDK 56. **Judgment call:** teams wanting one more field-tested cycle can stay on SDK 56 (React Native 0.85) — both are acceptable; don't mix SDK versions within one app. |
| React Native | **0.86** (via Expo SDK 57) | Pinned indirectly through the Expo SDK — don't hand-pin a bare React Native version inside an Expo-managed app. |

## Kit-wide lint & format tooling
| Dep | Pinned line | Why this line |
| --- | --- | --- |
| ESLint | **10.x** (10.7.0) | Current stable major (released Feb 2026); flat config (`eslint.config.mjs`) has been the default since ESLint 9 and continues unchanged into 10 — the monorepo skeleton's flat config from Step 1 needs no changes for this pin. **Judgment call:** this line was previously drafted as "9.x" before verification; 10.x was already current stable at pin time and typescript-eslint 8.65.x supports it (`peerDependencies.eslint: "^8.57.0 \|\| ^9.0.0 \|\| ^10.0.0"`), so pin the true current line rather than the stale draft value. |
| typescript-eslint | **8.65.x** (8.65.0) | Current stable; supports both TypeScript 6.0.x (`peerDependencies.typescript: ">=4.8.4 <6.1.0"`) and ESLint 10 — the pair every TS package in the kit layers on top of the JS-only base config (see `eslint.config.mjs`'s own note). |
| Prettier | **3.9.x** (3.9.6) | Current stable major; also orval's own formatting peer dependency (`peerDependencies.prettier: ">=3.0.0"`) for its generated output. |
| vitest | **4.1.x** (4.1.10) | Current stable line (`latest` dist-tag); v5 exists only as a `5.0.0-beta.x` prerelease, not GA — do not adopt pre-GA. Runs `packages/api-client`'s test suite (`vitest run`) against a stubbed global `fetch`. |

## Data
| Dep | Pinned line | Why this line |
| --- | --- | --- |
| PostgreSQL | **18.x** (18.4) | Current major/stable. Postgres 19 is beta-only (GA expected ~Sep/Oct 2026) — do not target it yet. |

## Infra
| Dep | Pinned line | Why this line |
| --- | --- | --- |
| Terraform (core) | **~> 1.15** | Latest supported minor as of this pin; 1.16 exists only as an alpha. See `references/infra/terraform.md`. |
| Terraform AWS provider | **~> 6.55** (major `6.x`) | Current provider major; pin the major with a floor, let patches float per module. |

## Containers
| Dep | Pinned line | Why this line |
| --- | --- | --- |
| Python base image | **`python:3.13-slim-bookworm`** | Matches the Python pin above; explicit Debian codename (not floating `slim`) for reproducible builds. |
| Node base image | **`node:24-bookworm-slim`** | Matches the Node LTS pin above; Bookworm remains in full support through 2026+. |
| Postgres image (dev compose) | **`postgres:18-bookworm`** | Matches the "Data" row's PostgreSQL 18.x pin, Bookworm-based for consistency with the two rows above. Used by `templates/backend/fastapi/docker-compose.yml` (Stage 3 #26, Step 4's dev-run seam) AND `templates/backend/django/docker-compose.yml` (Stage 4 #27, Step 4's own dev-run seam — the same pin, cited once, reused rather than re-pinned separately per backend track). **Judgment call:** a sandboxed/offline verification environment without registry access may only have Postgres 16 installed locally (`pg_ctlcluster`) to prove the alembic/asyncpg (FastAPI) or migrate/psycopg (Django) path against directly — that's a verification-environment substitute, not a repin of either compose file, both of which stay on the matrix's real 18.x line. |
| uv base image (Dockerfile) | **`ghcr.io/astral-sh/uv:0.11.31`** | Same uv version already pinned above ("Security tooling" row, for CI's `deps` job) — one uv version across the kit rather than a Docker-only drift. `templates/backend/fastapi/Dockerfile` AND `templates/backend/django/Dockerfile` both copy the `uv`/`uvx` binaries out of this image via `COPY --from=`, per uv's own documented Docker integration pattern. |

## Security tooling (CI scanners)
The pin set `assets/workflows/security.yml` (the firm's security-gate workflow, `references/security/secure-baseline.md`'s CI-scanning section) runs against. Each tool's **binary/CLI** is invoked at an exact pinned version so a gate's pass/fail is reproducible run to run — that part is not a moving target. **Caveat:** semgrep's two rulesets (`p/ci`, `p/owasp-top-ten`) are pulled live from Semgrep's public registry on every run and are *not* pinned — they float by design, since a pinned/vendored ruleset would mean either a Semgrep AppSec Platform login (to pull a fixed registry snapshot) or hand-maintaining the rule set ourselves. Accepted tradeoff for staying unauthenticated on `GITHUB_TOKEN` only: the semgrep binary version is reproducible, its finding set is not.

| Dep | Pinned line | Why this line |
| --- | --- | --- |
| bandit | **1.9.4** | Current stable (PyPI, Feb 25 2026); Python SAST — AST-based checks for common insecure patterns (`subprocess` with `shell=True`, weak hashes, hardcoded binds). Installed via `pip install bandit==1.9.4`, not a dedicated Action — PyCQA doesn't publish one. |
| semgrep | **1.170.1** | Current stable (PyPI, Jul 21 2026). Multi-language SAST. Run as `semgrep scan --config=p/ci --config=p/owasp-top-ten`, the free public-registry rulesets — deliberately not `--config=auto`, which now expects a Semgrep AppSec Platform login; `p/ci` and `p/owasp-top-ten` are documented as usable from the CLI with no account, keeping the gate on the default `GITHUB_TOKEN` only. |
| pip-audit | **2.10.1** (`pypa/gh-action-pip-audit@v1.1.0`) | Current stable (PyPI, Jun 10 2026); official PyPA action, current tag (Aug 2024, still latest). Dependency-CVE scan for Python; requirements/`pyproject.toml` resolved against the PyPI Advisory Database + OSV. Consumes a `requirements.txt` — for a uv-managed project with no committed one, the `deps` job resolves `uv.lock` to that format first via the `uv` row below. |
| uv | **0.11.31** | Current stable (PyPI, Jul 22 2026). Not itself a security scanner — pinned here because `assets/workflows/security.yml`'s `deps` job installs it as a prerequisite step, to turn a uv-managed project's `pyproject.toml`/`uv.lock` (the firm-standard Python setup — no committed `requirements.txt`; see Backend — Python) into a `requirements.txt` pip-audit can read: `uv export --frozen --no-emit-project --format requirements.txt`. `--frozen` deliberately errors out on a missing/stale lockfile rather than silently re-resolving one, so a CVE gate always audits what's actually locked. |
| pnpm audit | *(bundled with the pinned pnpm — see Frontend/web row)* | For the JS stack, **judgment call:** use `pnpm audit` rather than adding a separate scanner (`osv-scanner`) — the kit already pins pnpm as its package manager, so the audit command ships for free with no new dependency to track on this matrix. Revisit if a project's `pnpm audit` false-positive rate becomes a problem; `google/osv-scanner-action` is the fallback. |
| gitleaks | **v8.30.1** (CLI, via `ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f`) | Current stable (GitHub releases, Mar 21 2026). Pinned by digest (the multi-arch manifest-list digest, resolved via `docker buildx imagetools inspect`), not just the tag, so the image can't move under the pin. **Judgment call:** run the pinned Docker image directly (`docker run ... git`) rather than `gitleaks/gitleaks-action@v3` — the Action is free only for personal-account repos; an org-owned repo (this one included) needs a `GITLEAKS_LICENSE` secret for more than one scanned repo. Running the raw MIT-licensed binary keeps the gate on the default `GITHUB_TOKEN` with no extra secret, matching the "self-contained payload" constraint every `assets/workflows/*.yml` file is held to. |
| checkov | **3.2.526** | Current stable (PyPI, Jun 30 2026). Chosen as the **primary IaC scanner** (Terraform, at minimum). **Judgment call — tfsec vs. checkov:** tfsec is frozen — Aqua Security merged its check library into Trivy in 2024 and stopped adding new checks/Terraform-feature coverage there; picking it for new adoption in 2026 means picking a tool that's stopped moving. checkov (Prisma Cloud/Palo Alto Networks) is actively maintained with a materially larger, more frequently updated policy library. **Alternate:** Trivy already ships `trivy config` for IaC misconfiguration scanning and is already a pinned dependency below for the containers job — a project that wants one fewer tool in the pipeline can point `trivy config` at `infra/` instead of running checkov separately; the security workflow's `iac` job runs checkov by default. |
| trivy | **0.70.0** core, installed via trivy's own pinned install script (`contrib/install.sh -b /usr/local/bin v0.70.0`) | Current stable at the time this line was pinned; bundled with `aquasecurity/trivy-action@v0.36.0` originally, but the `containers` job now installs the CLI directly instead of using that Action — a project can have more than one Dockerfile, and building+scanning each one by its own path/context needs a shell loop, which a marketplace `uses:` step can't participate in. Trivy core version pin unchanged by that switch. Container image scanning. **Inspection-only in this sandbox** — see `assets/workflows/security.yml`'s `containers` job comment; the detect+build+scan shell logic was verified against fixture Dockerfiles (constructed commands echoed), not by actually running `docker build`/`trivy image` (no dockerd socket in-sandbox). |

## How blocks consume this
- A block's `README.md` `versions-pinned-to` field points at the row(s) here it depends on — it does not restate the version.
- Lockfiles (`uv.lock` / `poetry.lock`, `pnpm-lock.yaml`) are the enforcement mechanism; this matrix is what a fresh `pnpm add` / `uv add` should resolve to, not a substitute for pinning in the manifest.
- Security-relevant pins here (TLS libs, auth deps, the AWS provider) are also the versions `references/security/secure-baseline.md` assumes are in place — bumping a security-relevant dep off this matrix without reviewing that doc is a gap, not a shortcut.
- Bumping a line here is a deliberate, matrix-wide change (re-verify against official sources, update `last-verified`), not a per-block decision.
