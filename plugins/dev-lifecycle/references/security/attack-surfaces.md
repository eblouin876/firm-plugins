<!--
library: attack-surfaces
versions-covered: "OWASP ASVS 5.0, WSTG v4.2, Top 10:2025"
last-verified: 2026-07-12
provenance: manual
sources:
  - https://owasp.org/www-project-application-security-verification-standard/
  - https://owasp.org/www-project-web-security-testing-guide/
  - https://owasp.org/Top10/
-->

# Attack-surface taxonomy (by application type)

Loaded by the `security-audit` skill after it fingerprints the application. For each application type: the surfaces to enumerate and what evidence of a control ("handled") looks like. A project is often several types at once — a web app is a frontend **and** an API **and** usually workers and CI — so union the applicable sections and skip the rest. Per-surface vulnerability checks live in `owasp.md`; this doc is the map of *where to look*.

## Contents
- Cross-cutting (every application type)
- Web frontend (SPA or server-rendered)
- HTTP API / backend service
- Background workers / scheduled jobs
- CLI tool
- Library / package
- Infrastructure / IaC / CI-CD
- The evidence standard for "handled"

## Cross-cutting (every application type)

- **Secrets & credentials** — in code, config, git history, logs, error output. Handled: secrets come from env/secret manager; env files gitignored; nothing plaintext in the tree or history; CI secret scanning if configured.
- **Dependency supply chain** — manifest + lockfile, known CVEs, unpinned or unmaintained packages. Handled: lockfile committed and consistent; a CI audit gate or clean native audit (`pip-audit`, `npm audit`). Remediation is the `dependency-maintenance` skill's lane.
- **Error & exception handling** — fail closed, not open; no stack traces/SQL/paths leaked to users (owasp.md A10).
- **Logging & alerting** — auth failures, access denials, and privilege changes logged; secrets/tokens/excess PII *not* logged (A09).

## Web frontend (SPA or server-rendered)

- **Rendering of user or remote content (XSS)** — `dangerouslySetInnerHTML`, `innerHTML`, `v-html`, template autoescape bypasses (`| safe`, `mark_safe`). Handled: escaped-by-default rendering everywhere; a sanitizer (e.g. DOMPurify) on any deliberate raw-HTML path; CSP as backstop.
- **Client-side auth state** — where tokens/sessions live and how they die. Handled: httpOnly+Secure+SameSite cookies (or short-lived tokens with refresh); no tokens in URLs, localStorage-without-tradeoff-awareness, or logs; logout actually clears state.
- **CSRF** (cookie-based sessions) — Handled: SameSite plus CSRF tokens on state-changing routes.
- **Security headers** — CSP, `frame-ancestors`/X-Frame-Options (clickjacking), referrer policy. Handled: set at the server/proxy layer, verified present.
- **Client-side authorization** — hidden UI is not access control. Handled: every privileged action re-checked server-side (assess with the API section).
- **Secrets in the bundle** — API keys in JS, prod source maps, `NEXT_PUBLIC_`/`VITE_` vars holding things that aren't public. Handled: only true publishables in client-reachable config.
- **Third-party scripts** — minimal set, SRI where loaded from CDNs.
- **`postMessage`/`BroadcastChannel` handlers** — origin validated before trusting data.
- **Open redirects** — `returnUrl`-style params validated against an allowlist.

## HTTP API / backend service

- **Authentication coverage** — every non-public route behind auth; token validation complete (signature, expiry, issuer/audience); brute-force protection on credential endpoints.
- **Authorization & object access (IDOR)** — ownership/tenancy verified on every fetch/mutation by ID; roles enforced server-side; mass assignment blocked (client can't set `is_admin`). The #1 class — check route by route.
- **Input channels** — body, query, path, headers, uploads all validated at the boundary (Pydantic/schema layer), with size limits. Injection per owasp.md A05: raw SQL `text()` with interpolation, shell-outs, path traversal.
- **File uploads** — type/size validated, filenames sanitized, stored outside the webroot, never executed or reflected raw.
- **Outbound requests from user input (SSRF)** — target allowlisted; can't be coerced to internal addresses/metadata endpoints.
- **Inbound webhooks** — signature verified, replay-protected, idempotent.
- **Rate limiting & abuse controls** — on auth, expensive, and destructive endpoints.
- **CORS** — explicit origins; never wildcard with credentials.
- **Session/token lifecycle** — sensible expiry; rotation; revocation on logout/password change.
- **Admin & debug surfaces** — auto docs (`/docs`), debug toolbars, metrics/health detail: gated or disabled in prod.
- **Multi-tenancy boundary** (if applicable) — every query tenant-scoped; test the cross-tenant read *and* write.
- **Error responses** — generic to clients, detailed server-side only.

## Background workers / scheduled jobs

- **Job payloads are untrusted input** — validated like HTTP input; no unsafe deserialization (pickle & friends) of anything user-influenced.
- **Enqueue access** — who can put jobs on the queue; broker not exposed publicly, authenticated.
- **Privilege level** — workers often hold broad DB access: least privilege, and jobs re-check authorization rather than trusting the enqueuer.
- **Idempotency & replay** — retries/replays can't double-apply sensitive effects (payments, emails, privilege changes).
- **Secrets in job args and logs** — payloads and worker logs don't carry credentials.
- **Scheduled fetches** — data pulled from remote sources treated as untrusted; integrity checked where it drives decisions.

## CLI tool

- **Argument / stdin / file input** — parsed defensively; no injection into shell-outs; path traversal from user-supplied paths.
- **Config file trust** — config read from CWD means a hostile repo can plant one; precedence explicit, contents validated, no code execution from config.
- **Secrets handling** — tokens via env/keychain/file with tight permissions, not flags (visible in `ps` and shell history); nothing echoed to output.
- **Output & terminal** — untrusted data can't inject terminal escapes; output intended for `eval` treated as a contract.
- **Install/update path** — `curl | bash` and unsigned self-updates are findings; checksums/signatures are the control.
- **Temp files** — created with `mkstemp`-style safety, not predictable paths.

## Library / package

- **The public API is the trust boundary** — which inputs are documented as trusted vs untrusted, and validation matches that contract.
- **Defaults** — secure by default; an insecure opt-out beats an insecure default consumers won't change.
- **No eval/deserialization of caller data** unless that is explicitly the product, hardened accordingly.
- **Resource exhaustion** — ReDoS in exposed regexes; unbounded memory/recursion on attacker-shaped input.
- **Transitive footprint** — consumers inherit the dependency tree; keep it minimal and audited.
- **Release integrity** — publishing gated (2FA/trusted publisher), provenance where the registry supports it.

## Infrastructure / IaC / CI-CD

- **Workflow injection** — untrusted PR titles/branch names/issue text interpolated into `run:` blocks; `pull_request_target` with checkout of PR code.
- **Actions supply chain** — third-party actions pinned to SHAs (not mutable tags); minimal `GITHUB_TOKEN` permissions per workflow; secrets not exposed to fork PRs.
- **IaC posture** — public buckets, 0.0.0.0/0 ingress, wildcard IAM, unencrypted storage.
- **Containers** — current base images, non-root runtime, no secrets baked into layers or build args.
- **Deployment surface** — exposed ports/admin panels, TLS config, default credentials on bundled services.
- **CI secrets hygiene** — scoped per environment; never printed to logs.

## The evidence standard for "handled"

A surface is ✅ Handled only with concrete evidence: the control's location (`file:line` or config/CI path) **and** confirmation it is actually wired in — middleware registered, decorator applied to the routes in question, the CI gate actually running. "The framework probably does this" is not evidence; find the setting that turns it on. Credit partial coverage honestly ("auth on all routes except `/export`") — the gap is the finding, the coverage is still credited.

---
<!--
Authoring rules for this reference:
- This is a *where-to-look* map, not a vulnerability checklist — per-surface checks live in owasp.md.
- Keep sections keyed to application types so the security-audit skill can load/apply only what the fingerprint says.
- Update `last-verified` (and sources) whenever revised; the freshness audit reads the header above.
-->
