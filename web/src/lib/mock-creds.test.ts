import { describe, expect, it } from "vitest";

import { findMockUser, MOCK_USERS, verifyMockCredentials } from "./mock-creds";

describe("mock-creds", () => {
  it("provides standard role mock accounts", () => {
    expect(MOCK_USERS.length).toBeGreaterThanOrEqual(4);
    const admin = findMockUser("admin@carbonstack.io");
    expect(admin).toBeDefined();
    expect(admin?.role).toBe("owner");

    const analyst = findMockUser("analyst@carbonstack.io");
    expect(analyst?.role).toBe("analyst");

    const verifier = findMockUser("verifier@carbonstack.io");
    expect(verifier?.role).toBe("reviewer");

    const field = findMockUser("field@carbonstack.io");
    expect(field?.role).toBe("field_agent");
  });

  it("verifies mock password correctly", () => {
    const verified = verifyMockCredentials("admin@carbonstack.io", "CarbonStack2026!");
    expect(verified).not.toBeNull();
    expect(verified?.email).toBe("admin@carbonstack.io");

    const failed = verifyMockCredentials("admin@carbonstack.io", "wrongpassword123");
    expect(failed).toBeNull();
  });
});

