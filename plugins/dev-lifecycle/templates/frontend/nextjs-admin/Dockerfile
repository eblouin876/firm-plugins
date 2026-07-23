# Multi-stage build for the Next.js (App Router) ADMIN app. Clone of
# templates/frontend/nextjs/Dockerfile with every apps/web -> apps/admin,
# "web..." -> "admin...", and the runtime port bumped to 3001 (so this app's
# container can run side by side with apps/web's on 3000 without a port
# collision — the two are separate deployables, see docs/fragment.md's
# Deployment section). Unlike the Vite SPA (a static bundle served by a
# zero-dependency file server), Next needs a Node runtime in production for
# `next start` (rewrites/headers are server features) — so this is the
# PRIMARY production path for this block, not a secondary option.
#
# BUILD CONTEXT IS THE MONOREPO ROOT (not apps/admin), because this app
# imports the `@repo/api-client` and `@repo/web-shared` workspace packages
# and pnpm must see the whole workspace to resolve + build them. Build it as:
#
#     docker build -f apps/admin/Dockerfile -t admin .
#
# (run from the project root). The root `.dockerignore` keeps node_modules/
# .next out of the context; apps/admin/.dockerignore mirrors it for
# BuildKit's per-Dockerfile ignore.
#
# Base image per references/compatibility-matrix.md "Containers"
# (node:24-bookworm-slim) — the same Node LTS line the app is pinned to.

# --- build stage ----------------------------------------------------------
FROM node:24-bookworm-slim AS build

# pnpm via corepack, at the version the root package.json's `packageManager`
# field pins — no global npm install, no separately-drifting pnpm version.
RUN corepack enable
ENV CI=1

WORKDIR /repo

# Copy the whole workspace (the root .dockerignore already excludes
# node_modules/.next/etc). A project that commits a lockfile gets a
# reproducible install; without one, pnpm resolves fresh in this layer.
COPY . .

# The only value baked into the browser bundle is the PUBLIC API base URL
# (NEXT_PUBLIC_-prefixed, so Next inlines it at build time). It is NOT a
# secret — never pass tokens, keys, or passwords as build args here; they
# would end up readable in the shipped JS. Empty default = same-origin
# relative URLs (edge-routed API).
ARG NEXT_PUBLIC_API_BASE_URL=""
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

# Install the workspace, then build `admin` AND its workspace dependencies
# (`admin...` selects admin + everything it depends on) in topological order:
# @repo/api-client -> @repo/web-shared -> admin. next.config.ts's
# `output: "standalone"` makes this emit a minimal, self-contained server at
# apps/admin/.next/standalone/ tracing only the node_modules this app
# actually needs, rather than the whole workspace install.
RUN pnpm install
RUN pnpm --filter "admin..." run build

# --- runtime stage --------------------------------------------------------
FROM node:24-bookworm-slim AS runtime

# Least privilege: run as the unprivileged `node` user the base image already
# provides (uid 1000), never root — matches references/security/secure-baseline.md.
WORKDIR /app

# Ship ONLY the standalone server Next traced (its own minimal node_modules
# subset + server.js) plus the static assets and public files that
# `output: "standalone"` deliberately excludes from the trace and must be
# copied alongside it (see Next's own documented standalone-output layout).
# No source, no full workspace node_modules, no secret. The standalone
# tracer preserves the monorepo-relative path (apps/admin/...) because this
# app is built inside a pnpm workspace, not a standalone Next project.
COPY --from=build /repo/apps/admin/.next/standalone ./
COPY --from=build /repo/apps/admin/.next/static ./apps/admin/.next/static

# PORT 3001 (not 3000): this app is a SECOND, separate deployable from
# apps/web — running both locally (e.g. templates/monorepo/docker-compose.yml's
# commented `admin` service) must not collide with apps/web's own 3000.
ENV NODE_ENV=production \
    PORT=3001 \
    HOSTNAME=0.0.0.0

USER node
EXPOSE 3001
CMD ["node", "apps/admin/server.js"]
