# Secondary container option for the web app: a multi-stage build that produces
# a small static-serve image. The PRIMARY production path is a static/CDN host
# (S3 + CloudFront) serving the `vite build` output directly — see
# docs/fragment.md's Deployment section; this image is the alternative for a
# container platform.
#
# BUILD CONTEXT IS THE MONOREPO ROOT (not apps/web), because this app imports
# the `@repo/api-client` and `@repo/web-shared` workspace packages and pnpm must
# see the whole workspace to resolve + build them. Build it as:
#
#     docker build -f apps/web/Dockerfile -t web .
#
# (run from the project root). The root `.dockerignore` keeps node_modules/dist
# out of the context; apps/web/.dockerignore mirrors it for BuildKit's
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
# node_modules/dist/etc). A project that commits a lockfile gets a reproducible
# install; without one, pnpm resolves fresh in this layer.
COPY . .

# The only value baked into the browser bundle is the PUBLIC API base URL
# (VITE_-prefixed, so Vite inlines it). It is NOT a secret — never pass tokens,
# keys, or passwords as build args here; they would end up readable in the
# shipped JS. Empty default = same-origin relative URLs (edge-routed API).
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

# Install the workspace, then build `web` AND its workspace dependencies
# (`web...` selects web + everything it depends on) in topological order:
# @repo/api-client -> @repo/web-shared -> web.
RUN pnpm install
RUN pnpm --filter "web..." run build

# --- runtime stage --------------------------------------------------------
FROM node:24-bookworm-slim AS runtime

# Least privilege: run as the unprivileged `node` user the base image already
# provides (uid 1000), never root — matches references/security/secure-baseline.md.
WORKDIR /app

# Ship ONLY the built static assets + the zero-dependency static server. No
# source, no node_modules, no secret — the image is the public bundle plus a
# tiny SPA-fallback file server.
COPY --from=build /repo/apps/web/dist ./dist
COPY --from=build /repo/apps/web/serve.mjs ./serve.mjs

ENV NODE_ENV=production \
    PORT=8080 \
    WEB_ROOT=/app/dist

USER node
EXPOSE 8080

CMD ["node", "serve.mjs"]
