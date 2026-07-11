<!--
library: github-actions
versions-covered: "n/a"
last-verified: 2026-07-09
provenance: manual
sources: []
-->

# CI/CD pipeline conventions

Guidance for the build/test/deploy pipeline and its gates. Default platform: GitHub Actions. The project's existing pipeline overrides anything here.

## Contents
- Pipeline shape
- The gates (this is the point)
- Build, tag, push
- Deploy stage
- GitHub Actions specifics
- Right-sizing

## Pipeline shape
A fully built-out pipeline handles: lint → type-check → test → security scan → build image → push to registry → deploy. Continuous integration is the first half (validate every push/PR); continuous deployment is the second (ship automatically when the gates pass, optionally behind a manual approval for production).

- **On every push / PR:** run the gates (lint, types, tests, scans). These must pass for the PR to be mergeable.
- **On merge to the deploy branch:** re-run gates, build and push the image tagged by git SHA, then deploy.
- Use the same container image throughout — the artifact that passed tests is the artifact that deploys.

## The gates (this is the point)
Deployment is *gated*. A red gate blocks the deploy — never configure a pipeline that ships on failure.

1. **Lint & format:** the project's linters/formatters (Ruff/ESLint/Prettier) in check mode. Also lint the pipeline itself when the repo has one: `actionlint` on `.github/workflows/*` (it catches invalid expressions — e.g. `secrets` used in an `if:`, or an unknown self-hosted runner label needing an `.github/actionlint.yaml`) and `shellcheck` on any committed shell script. The build agent runs these locally before opening the PR (definition-of-done), and this gate is the backstop.
2. **Type-check:** `mypy`/`pyright` for Python, `tsc --noEmit` for TypeScript. Type errors fail the build.
3. **Tests:** the full suite (pytest, the JS test runner). Fail on any failure; enforce a coverage threshold if the project sets one. This gate runs the tests the build skills wrote — it only protects you if those tests exist and are meaningful.
4. **Security scans** — the automated counterpart to the code-review skill's security audit:
   - **Dependency scanning** for known-vulnerable packages (OWASP A03) — e.g. `pip-audit`, `npm audit`, or a scanner action.
   - **Image scanning** (Trivy/Grype/Docker Scout) on the built image.
   - **Secret detection** (gitleaks/trufflehog) so credentials never land in the repo or image.
   - **SAST** (e.g. CodeQL) where it fits, for injection and similar classes.
   - Set severity thresholds deliberately: fail on high/critical; triage the rest rather than blocking on noise.

Run independent gates in parallel for speed; cache dependencies and Docker layers.

## Build, tag, push
- Build the image only after the gates pass.
- Tag by immutable git SHA (and optionally a moving tag like `latest` or an environment name). SHA tags make every deploy traceable and every rollback addressable.
- Push to the project's registry (GitHub Container Registry, ECR, Artifact Registry, Docker Hub). Authenticate via CI secrets / OIDC, never hardcoded creds.

## Deploy stage
- Pull/reference the exact tested image by SHA and deploy it to the target.
- Run database migrations as an explicit, ordered step before/with the release (see backend Alembic conventions) — never implicitly, never skipped.
- Prefer a zero-downtime strategy the target supports (rolling, blue-green, canary). Verify health after rollout.
- Production deploys can sit behind a manual approval (GitHub Environments protection rules) — continuous delivery with a human gate — when full continuous deployment isn't wanted.
- Define rollback: redeploy the previous SHA, and have a plan for migrations that aren't trivially reversible.

## GitHub Actions specifics
- Workflows in `.github/workflows/*.yml`, triggered on `push`, `pull_request`, and environment events.
- **Pin action versions** (ideally by SHA, at least by major tag) — third-party actions are supply-chain surface.
- Use `secrets` for credentials and prefer **OIDC** federation to cloud providers over long-lived keys.
- Use **Environments** with protection rules and required reviewers for production; scope secrets per environment.
- Use a matrix for multi-version testing; cache (`actions/cache`, Docker layer caching / Build Cloud) to keep runs fast.
- Set least-privilege `permissions:` on the `GITHUB_TOKEN`.

## Right-sizing
- For a small app on a modern PaaS, the platform may handle build/deploy/preview/rollback itself — then CI is just the gates (lint/type/test/scan) and the platform does the rest. Don't build a bespoke deploy pipeline you don't need.
- Add complexity (multi-env promotion, canary, GitOps) only when the project's scale and risk justify it.
