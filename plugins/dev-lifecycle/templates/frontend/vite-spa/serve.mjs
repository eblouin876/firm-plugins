// Zero-dependency static file server for the built SPA (dist/). Used by the
// secondary container option (see Dockerfile) so the final image stays on the
// compatibility-matrix's pinned `node:24-bookworm-slim` base with NO extra
// runtime dependency and no unpinned web-server image to track.
//
// It does the two things a single-page app needs from a static host:
//   1. serves hashed assets with a long immutable cache, and
//   2. SPA history fallback — any path that isn't a real file is served
//      index.html (200) so client-side routes like /admin deep-link correctly.
// The PRIMARY production path is a real static/CDN host (S3 + CloudFront) with
// the same fallback rule configured at the edge (403/404 -> /index.html 200);
// see docs/fragment.md's Deployment section. This server is the container
// alternative, not a hardened multi-tenant web server.
import { createReadStream, promises as fs } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";

const DIST = resolve(process.env.WEB_ROOT ?? "./dist");
const PORT = Number(process.env.PORT ?? 8080);
const HOST = process.env.HOST ?? "0.0.0.0";

const CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".map": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
};

const sendFile = (res, filePath, status = 200) => {
  const type = CONTENT_TYPES[extname(filePath)] ?? "application/octet-stream";
  // Vite emits content-hashed asset filenames, so anything under /assets/ is
  // safe to cache immutably; everything else (index.html) must revalidate.
  const cacheControl = filePath.includes(`${join("/assets")}/`)
    ? "public, max-age=31536000, immutable"
    : "no-cache";
  res.writeHead(status, { "Content-Type": type, "Cache-Control": cacheControl });
  createReadStream(filePath).pipe(res);
};

const server = createServer((req, res) => {
  // Only GET/HEAD for a static host.
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405, { Allow: "GET, HEAD" }).end();
    return;
  }

  const urlPath = decodeURIComponent((req.url ?? "/").split("?")[0]);
  // Resolve within DIST and reject any traversal that escapes it.
  const candidate = normalize(join(DIST, urlPath));
  if (candidate !== DIST && !candidate.startsWith(DIST + "/")) {
    res.writeHead(403).end();
    return;
  }

  void (async () => {
    try {
      const target = urlPath === "/" ? join(DIST, "index.html") : candidate;
      const stat = await fs.stat(target).catch(() => null);
      if (stat?.isFile()) {
        sendFile(res, target);
        return;
      }
      // Not a real file: a request for an asset path that doesn't exist is a
      // genuine 404; anything else is a client-side route -> serve the SPA.
      if (extname(urlPath)) {
        res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" }).end("Not found");
        return;
      }
      sendFile(res, join(DIST, "index.html"));
    } catch {
      res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" }).end("Server error");
    }
  })();
});

server.listen(PORT, HOST, () => {
  console.log(`Serving ${DIST} on http://${HOST}:${PORT}`);
});
