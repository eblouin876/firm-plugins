// Public surface of @repo/api-client: the generated hooks/models, plus the
// mutator (exposed for tests/tooling — consumers normally only touch the
// hooks). Regenerated on `pnpm run generate`; add exports here as new
// generated tags land, rather than deep-importing into src/generated/*.
export * from "./generated/endpoints/auth/auth.js";
export * from "./generated/endpoints/admin/admin.js";
export * from "./generated/endpoints/blog/blog.js";
export * from "./generated/endpoints/health/health.js";
export * from "./generated/endpoints/items/items.js";
export * from "./generated/endpoints/moderation/moderation.js";
export * from "./generated/models/index.js";
export { configureApiClient, customFetch } from "./mutator.js";
export type { ApiClientResponse } from "./mutator.js";
