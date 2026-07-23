import { decodeAccessTokenClaims } from "./decodeAccessTokenClaims";

const b64url = (obj: unknown): string =>
  Buffer.from(JSON.stringify(obj)).toString("base64url");

/** Build a structurally-valid JWT (header.payload.signature) — signature is a
 *  dummy; decodeAccessTokenClaims never verifies it (UX-only). */
const makeJwt = (payload: unknown): string =>
  `${b64url({ alg: "HS256", typ: "JWT" })}.${b64url(payload)}.not-a-real-signature`;

describe("decodeAccessTokenClaims", () => {
  it("extracts sub and roles from a well-formed token", () => {
    const token = makeJwt({ sub: "user-123", roles: ["admin", "editor"] });
    expect(decodeAccessTokenClaims(token)).toEqual({
      sub: "user-123",
      roles: ["admin", "editor"],
    });
  });

  it("survives multi-byte (UTF-8) claim values", () => {
    const token = makeJwt({ sub: "usér-café", roles: ["管理者"] });
    expect(decodeAccessTokenClaims(token)).toEqual({ sub: "usér-café", roles: ["管理者"] });
  });

  it("defaults roles to [] and sub to null when the claims are absent", () => {
    const token = makeJwt({ iss: "someone" });
    expect(decodeAccessTokenClaims(token)).toEqual({ sub: null, roles: [] });
  });

  it("filters non-string entries out of the roles claim", () => {
    const token = makeJwt({ sub: "u1", roles: ["admin", 42, null, "editor"] });
    expect(decodeAccessTokenClaims(token).roles).toEqual(["admin", "editor"]);
  });

  it.each([null, undefined, "", "not-a-jwt", "only.two", "a.b.c.d.e"])(
    "returns empty claims (never throws) for malformed input %p",
    (input) => {
      expect(decodeAccessTokenClaims(input as string | null | undefined)).toEqual({
        sub: null,
        roles: [],
      });
    },
  );

  it("returns empty claims when the payload segment isn't valid base64/JSON", () => {
    expect(decodeAccessTokenClaims("header.@@@not-base64@@@.sig")).toEqual({
      sub: null,
      roles: [],
    });
  });
});
