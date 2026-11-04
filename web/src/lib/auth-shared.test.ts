import { describe, expect, it } from "vitest";

import { SIGNED_IN_ONLY, isEmail, notice, passwordProblem, safeNext, under } from "./auth-shared";

describe("safeNext", () => {
  it("keeps same-site paths", () => {
    expect(safeNext("/app/farms?x=1")).toBe("/app/farms?x=1");
    expect(safeNext("/invite/abc")).toBe("/invite/abc");
  });

  it("refuses anything that could leave the site", () => {
    for (const bad of ["https://evil.test", "//evil.test", "/\\evil.test", "evil", "", null, undefined]) {
      expect(safeNext(bad)).toBe("/app");
    }
    expect(safeNext("//evil.test", "/onboarding")).toBe("/onboarding");
  });
});

describe("under", () => {
  it("matches a path and its children, not lookalikes", () => {
    expect(under("/app", SIGNED_IN_ONLY)).toBe(true);
    expect(under("/app/profile", SIGNED_IN_ONLY)).toBe(true);
    expect(under("/reset-password", SIGNED_IN_ONLY)).toBe(true);
    expect(under("/apple", SIGNED_IN_ONLY)).toBe(false);
    expect(under("/verify/ABC-2025-1", SIGNED_IN_ONLY)).toBe(false);
  });
});

describe("passwordProblem", () => {
  it("wants at least ten characters", () => {
    expect(passwordProblem(null)).toMatch(/at least 10/);
    expect(passwordProblem("short")).toMatch(/at least 10/);
    expect(passwordProblem("long enough pass")).toBeNull();
  });

  it("refuses more than bcrypt reads, counted in bytes", () => {
    expect(passwordProblem("a".repeat(72))).toBeNull();
    expect(passwordProblem("a".repeat(73))).toMatch(/at most 72/);
    expect(passwordProblem("அ".repeat(25))).toMatch(/at most 72/); // 75 bytes in UTF-8
  });

  it("refuses the email address as the password", () => {
    expect(passwordProblem("Asha@acme.test", "asha@acme.test")).toMatch(/email/);
  });
});

describe("isEmail", () => {
  it("accepts plain addresses and refuses obvious junk", () => {
    expect(isEmail("asha@acme.test")).toBe(true);
    expect(isEmail("asha@acme")).toBe(false);
    expect(isEmail("asha acme@test.org")).toBe(false);
    expect(isEmail(null)).toBe(false);
  });
});

describe("notice", () => {
  it("says only what we wrote", () => {
    expect(notice("password-reset")).toMatch(/new password/);
    expect(notice("Your account was hacked, call +1 555")).toBeNull();
    expect(notice("toString")).toBeNull();
    expect(notice(undefined)).toBeNull();
  });
});
