/// <reference types="vite/client" />

// The typed surface of this app's build-time env. Only VITE_-prefixed vars
// are inlined into the browser bundle by Vite, and only PUBLIC values ever
// belong here — see .env.example. `VITE_API_BASE_URL` is optional: unset (the
// dev default) means same-origin relative URLs through the Vite dev proxy (see
// vite.config.ts), which is exactly what cookie-mode auth wants locally.
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
