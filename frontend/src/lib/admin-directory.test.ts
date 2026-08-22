import { beforeEach, describe, expect, it, vi } from "vitest";

const { getFirebaseServices } = vi.hoisted(() => ({ getFirebaseServices: vi.fn() }));
vi.mock("@/lib/firebase", () => ({ getFirebaseServices }));

import { AdminDirectoryError, loadAdminDirectory, parseAdminDirectoryResponse, validateAdminDirectoryFilters } from "./admin-directory";

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local-emulator");
  vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://127.0.0.1:8000");
  getFirebaseServices.mockReset();
});

describe("validateAdminDirectoryFilters", () => {
  it("accepts approved filters and normalizes search", () => {
    expect(validateAdminDirectoryFilters({ role: "staff", departmentId: "card_atm", active: false, search: "  Ada ", pageSize: 10 })).toEqual({
      role: "staff", departmentId: "card_atm", active: false, search: "Ada", pageSize: 10,
    });
  });

  it("rejects unknown, invalid, and Manager department filters", () => {
    expect(() => validateAdminDirectoryFilters({ unknown: "value" })).toThrowError(AdminDirectoryError);
    expect(validateAdminDirectoryFilters({ role: "customer" })).toEqual({ role: "customer" });
    expect(validateAdminDirectoryFilters({ role: "admin" })).toEqual({ role: "admin" });
    expect(() => validateAdminDirectoryFilters({ departmentId: "unknown" })).toThrowError(AdminDirectoryError);
    expect(() => validateAdminDirectoryFilters({ role: "manager", departmentId: "card_atm" })).toThrowError(AdminDirectoryError);
  });

  it("strictly parses all safe roles and rejects private or malformed fields", () => {
    const safe = {
      rows: [
        { email: "customer@example.test", displayName: "Customer", locale: "en", role: "customer", departmentId: null, active: true, setupStatus: "active" },
        { email: "staff@example.test", displayName: "Staff", locale: "my", role: "staff", departmentId: "card_atm", active: false, setupStatus: "pending_setup" },
        { email: "manager@example.test", displayName: "Manager", locale: "en", role: "manager", departmentId: null, active: true, setupStatus: "active" },
        { email: "admin@example.test", displayName: "Admin", locale: "en", role: "admin", departmentId: null, active: true, setupStatus: "active" },
      ],
      nextCursor: null,
      hasMore: false,
    };
    expect(parseAdminDirectoryResponse(safe).rows).toHaveLength(4);
    expect(() => parseAdminDirectoryResponse({ ...safe, rows: [{ ...safe.rows[0], uid: "private" }] })).toThrowError(AdminDirectoryError);
    expect(() => parseAdminDirectoryResponse({ ...safe, rows: [{ ...safe.rows[0], role: "owner" }] })).toThrowError(AdminDirectoryError);
  });
});

describe("loadAdminDirectory", () => {
  it("uses a fresh token and only approved query fields", async () => {
    const getIdToken = vi.fn().mockResolvedValue("fresh-token");
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ rows: [], nextCursor: null, hasMore: false }), { status: 200 }));
    await loadAdminDirectory({ role: "staff", departmentId: "card_atm", active: true, pageSize: 10 }, fetcher);
    expect(getIdToken).toHaveBeenCalledWith(true);
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/admin/users?role=staff&departmentId=card_atm&active=true&pageSize=10");
    expect(init.method).toBe("GET");
    expect(init.headers).toEqual({ Authorization: "Bearer fresh-token" });
  });

  it("fails validation before token or fetch and maps safe statuses", async () => {
    const getIdToken = vi.fn();
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    const fetcher = vi.fn();
    await expect(loadAdminDirectory({ role: "owner" }, fetcher)).rejects.toMatchObject({ code: "validation" });
    expect(getIdToken).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
    for (const [status, code] of [[401, "authentication"], [403, "permission"], [422, "validation"], [503, "unavailable"]] as const) {
      getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken: vi.fn().mockResolvedValue("token") } } });
      const failing = vi.fn().mockResolvedValue(new Response("{}", { status }));
      await expect(loadAdminDirectory({}, failing)).rejects.toMatchObject({ code });
    }
  });
});
