# Multi-stage build for the Next.js (App Router) web app. Unlike the Vite
# SPA (a static bundle served by a zero-dependency file server), Next needs a
# Node runtime in production for `next start` (rewrites/headers are server
# features) — so this is the PRIMARY production path for this block, not a
# secondary option.
#
# BUILD CONTEXT IS THE MONOREPO ROOT (not apps/web), because this app imports
# the `@repo/api-client` and `@repo/web-shared` workspace packages and pnpm
# must see the whole workspace to resolve + build them. Build it as:
#
#     docker build -f apps/web/Dockerfile -t web .
#
# (run from the project root). The root `.dockerignore` keeps node_modules/
# .next out of the context; apps/web/.dockerignore mirrors it for BuildKit's
# per-Dockerfile ignore.
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

# Install the workspace, then build `web` AND its workspace dependencies
# (`web...` selects web + everything it depends on) in topological order:
# @repo/api-client -> @repo/web-shared -> web. next.config.ts's
# `output: "standalone"` makes this emit a minimal, self-contained server at
# apps/web/.next/standalone/ tracing only the node_modules this app actually
# needs, rather than the whole workspace install.
RUN pnpm install
RUN pnpm --filter "web..." run build

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
# tracer preserves the monorepo-relative path (apps/web/...) because this
# app is built inside a pnpm workspace, not a standalone Next project.
COPY --from=build /repo/apps/web/.next/standalone ./
COPY --from=build /repo/apps/web/.next/static ./apps/web/.next/static

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
