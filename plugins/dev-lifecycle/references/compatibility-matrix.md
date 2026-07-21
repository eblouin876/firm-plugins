<!--
scope: cross-stack starter kit
versions-covered: "Stage 0 kit-wide pin set, 2026-07"
last-verified: 2026-07-21
provenance: manual
sources:
  - https://pypi.org/project/fastapi/
  - https://pypi.org/project/pydantic/
  - https://www.sqlalchemy.org/blog/2026/04/16/sqlalchemy-2.1.0b2-released/
  - https://alembic.sqlalchemy.org/en/latest/changelog.html
  - https://www.djangoproject.com/download/
  - https://www.django-rest-framework.org/community/release-notes/
  - https://drf-spectacular.readthedocs.io/
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
-->

# Compatibility matrix

**The keystone reference.** A pinned, known-good version SET spanning the whole starter kit. Every template block and catalog component pins to this matrix — a block does not choose its own version of a kit-wide dependency. When a block's `versions-pinned-to` and this matrix disagree, this matrix wins; update the block. Cross-links `references/security/secure-baseline.md` for the security posture these pins are expected to run under.

## Contents
- Version check (do this first)
- Backend — Python
- Backend — Django track
- Frontend / web
- Mobile
- Data
- Infra
- Containers

## Version check (do this first)
Re-verify against official release notes/registries before bumping any line — recall is not a source. Two lines are deliberately held back from the newest available release; see the judgment calls inline. Re-run this check at least once a quarter or when a new template block is authored, whichever is sooner.

## Backend — Python
| Dep | Pinned line | Why this line |
| --- | --- | --- |
| Python | **3.13.x** | Latest stable with a mature C-extension/wheel ecosystem; 3.14 (released Oct 2025) is current but young for some third-party wheels — reassess next quarter. |
| FastAPI | **0.139.x** | Latest release line (0.139.2, Jul 2026); still pre-1.0, so pin the minor, not just the major. |
| Pydantic | **v2, 2.13.x** | Pydantic v2 only — v1 is a different library. 2.13.x is current stable; a 2.14 alpha exists but isn't GA. |
| SQLAlchemy | **2.0.x** (2.0.51) | The 2.0 style (`Mapped[]`, `select()`) is the baseline every block writes to. 2.1 is beta-only (`0b2`) as of this pin — do not adopt pre-GA. |
| Alembic | **1.18.x** | Tracks SQLAlchemy 2.0; current stable. |

## Backend — Django track
| Dep | Pinned line | Why this line |
| --- | --- | --- |
| Django | **5.2 LTS** | LTS branch, supported through Apr 2028 — the right default for a starter kit over a non-LTS feature release. |
| Django REST Framework | **3.17.x** | Current stable, tracks Django 5.2. |
| drf-spectacular | **0.30.x** | OpenAPI 3 schema generation for DRF; current stable, keep in lockstep with DRF. |

## Frontend / web
| Dep | Pinned line | Why this line |
| --- | --- | --- |
| Node.js | **24.x LTS** ("Krypton") | Active LTS as of this pin. Node 26 exists as Current but does not enter LTS until Oct 2026 — don't build the kit's baseline on it yet. |
| pnpm | **11.x** | Current stable major (dist-tag `latest`); newer store format and native registry commands. |
| TypeScript | **6.0** | TS 7.0 (Go-native compiler, ~10x faster) shipped Jul 9 2026 — 12 days before this pin. Held back one release deliberately: editor/lint-plugin ecosystem is still catching up to the native port. Revisit next quarter. |
| React | **19.x** (19.2.x) | Current stable major; Actions/`use()` are the baseline idiom set. |
| Vite | **8.x** (8.1.x) | Default bundler is now Rolldown (Rust) — faster cold start/HMR than Vite 7's Rollup default. |
| Next.js (App Router) | **16.x** (16.2.x) | App Router is the only sensible default at this line (Pages Router is maintenance-mode); Turbopack is the default bundler for `dev` and `build`. |

## Mobile
| Dep | Pinned line | Why this line |
| --- | --- | --- |
| Expo SDK | **57** | Current stable (released Jun 30 2026), ships React Native 0.86 as a small, non-breaking upgrade over SDK 56. **Judgment call:** teams wanting one more field-tested cycle can stay on SDK 56 (React Native 0.85) — both are acceptable; don't mix SDK versions within one app. |
| React Native | **0.86** (via Expo SDK 57) | Pinned indirectly through the Expo SDK — don't hand-pin a bare React Native version inside an Expo-managed app. |

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

## How blocks consume this
- A block's `README.md` `versions-pinned-to` field points at the row(s) here it depends on — it does not restate the version.
- Lockfiles (`uv.lock` / `poetry.lock`, `pnpm-lock.yaml`) are the enforcement mechanism; this matrix is what a fresh `pnpm add` / `uv add` should resolve to, not a substitute for pinning in the manifest.
- Security-relevant pins here (TLS libs, auth deps, the AWS provider) are also the versions `references/security/secure-baseline.md` assumes are in place — bumping a security-relevant dep off this matrix without reviewing that doc is a gap, not a shortcut.
- Bumping a line here is a deliberate, matrix-wide change (re-verify against official sources, update `last-verified`), not a per-block decision.
