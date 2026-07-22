// orval config: React Query hooks generated with a custom `fetch` mutator
// (no axios). `input.target` points at the committed sample fixture until
// Stage 3 swaps it for the live backend OpenAPI schema — see README.md.
import { defineConfig } from "orval";

export default defineConfig({
  apiClient: {
    input: {
      target: "./openapi.sample.json",
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
