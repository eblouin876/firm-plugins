// orval config: React Query hooks generated with a custom `fetch` mutator
// (no axios). `input.target` points at the committed, LIVE-exported
// backend OpenAPI schema (see README.md's "Stage 3: the live schema") —
// `openapi.json` here is the output of the FastAPI block's
// `python -m app.export_openapi`, not a hand-built fixture.
import { defineConfig } from "orval";

export default defineConfig({
  apiClient: {
    input: {
      target: "./openapi.json",
    },
    output: {
      mode: "tags-split",
      target: "./src/generated/endpoints",
      schemas: "./src/generated/models",
      client: "react-query",
      httpClient: "fetch",
      clean: true,
      override: {
        mutator: {
          path: "./src/mutator.ts",
          name: "customFetch",
        },
      },
    },
  },
});
