import { beforeEach, describe, expect, it, vi } from "vitest";

const { getFirebaseServices } = vi.hoisted(() => ({ getFirebaseServices: vi.fn() }));
vi.mock("@/lib/firebase", () => ({ getFirebaseServices }));

import { AdminDirectoryError, loadAdminDirectory, loadAdminLifecycleEligibility, parseAdminDirectoryResponse, parseAdminLifecycleEligibility, validateAdminDirectoryFilters } from "./admin-directory";

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
        { accountRef: "acct_v1_0000000000000000000000000000000000000000000000000000000000000000", email: "customer@example.test", displayName: "Customer", locale: "en", role: "customer", departmentId: null, active: true, accountState: "active" },
        { accountRef: "acct_v1_1111111111111111111111111111111111111111111111111111111111111111", email: "staff@example.test", displayName: "Staff", locale: "my", role: "staff", departmentId: "card_atm", active: false, accountState: "pending_setup" },
        { accountRef: "acct_v1_2222222222222222222222222222222222222222222222222222222222222222", email: "manager@example.test", displayName: "Manager", locale: "en", role: "manager", departmentId: null, active: true, accountState: "active" },
        { accountRef: "acct_v1_3333333333333333333333333333333333333333333333333333333333333333", email: "admin@example.test", displayName: "Admin", locale: "en", role: "admin", departmentId: null, active: true, accountState: "active" },
      ],
      nextCursor: null,
      hasMore: false,
    };
    expect(parseAdminDirectoryResponse(safe).rows).toHaveLength(4);
    expect(() => parseAdminDirectoryResponse({ ...safe, rows: [{ ...safe.rows[0], uid: "private" }] })).toThrowError(AdminDirectoryError);
    expect(() => parseAdminDirectoryResponse({ ...safe, rows: [{ ...safe.rows[0], role: "owner" }] })).toThrowError(AdminDirectoryError);
    expect(() => parseAdminDirectoryResponse({ ...safe, rows: [{ ...safe.rows[0], accountRef: "private" }] })).toThrowError(AdminDirectoryError);
    expect(() => parseAdminDirectoryResponse({ ...safe, rows: [{ ...safe.rows[0], setupStatus: "active" }] })).toThrowError(AdminDirectoryError);
  });

  it("enforces account-state combinations and rejects non-enumerable, inherited, and symbol fields", () => {
    const row = { accountRef: "acct_v1_0000000000000000000000000000000000000000000000000000000000000000", email: "customer@example.test", displayName: "Customer", locale: "en", role: "customer", departmentId: null, active: false, accountState: "disabled" };
    const response = { rows: [row], nextCursor: null, hasMore: false };
    expect(parseAdminDirectoryResponse(response).rows[0].accountState).toBe("disabled");
    for (const accountState of ["pending_setup", "active", "unknown", " disabled"] as const) {
      expect(() => parseAdminDirectoryResponse({ ...response, rows: [{ ...row, accountState }] })).toThrowError(AdminDirectoryError);
    }
    expect(() => parseAdminDirectoryResponse({ ...response, rows: [{ ...row, active: true, accountState: "disabled" }] })).toThrowError(AdminDirectoryError);
    expect(() => parseAdminDirectoryResponse({ ...response, rows: [{ ...row, active: false, accountState: "active" }] })).toThrowError(AdminDirectoryError);
    expect(() => parseAdminDirectoryResponse({ ...response, rows: [{ ...row, role: "customer", accountState: "pending_setup" }] })).toThrowError(AdminDirectoryError);
    const hidden = { ...row };
    Object.defineProperty(hidden, "accountState", { value: "disabled", enumerable: false });
    expect(() => parseAdminDirectoryResponse({ ...response, rows: [hidden] })).toThrowError(AdminDirectoryError);
    const inherited = Object.create({ accountState: "disabled" });
    Object.assign(inherited, row);
    delete inherited.accountState;
    expect(() => parseAdminDirectoryResponse({ ...response, rows: [inherited] })).toThrowError(AdminDirectoryError);
    const symbolRow = { ...row, [Symbol("private")]: "secret" };
    expect(() => parseAdminDirectoryResponse({ ...response, rows: [symbolRow] })).toThrowError(AdminDirectoryError);
  });

  it("accepts every approved state only with its required access and role semantics", () => {
    const base = { accountRef: "acct_v1_0000000000000000000000000000000000000000000000000000000000000000", email: "user@example.test", displayName: "User", locale: "en", departmentId: null };
    const rows = [
      { ...base, role: "customer", active: true, accountState: "active" },
      { ...base, role: "staff", departmentId: "card_atm", active: true, accountState: "active" },
      { ...base, role: "manager", active: true, accountState: "active" },
      { ...base, role: "admin", active: true, accountState: "active" },
      { ...base, role: "staff", departmentId: "card_atm", active: false, accountState: "pending_setup" },
      { ...base, role: "manager", active: false, accountState: "pending_setup" },
      { ...base, role: "customer", active: false, accountState: "disabled" },
      { ...base, role: "staff", departmentId: "card_atm", active: false, accountState: "disabled" },
      { ...base, role: "manager", active: false, accountState: "inactive_unverified" },
      { ...base, role: "admin", active: false, accountState: "inactive_unverified" },
    ];
    expect(parseAdminDirectoryResponse({ rows, nextCursor: null, hasMore: false }).rows).toHaveLength(rows.length);
  });
});

describe("lifecycle eligibility", () => {
  const accountRef = "acct_v1_0000000000000000000000000000000000000000000000000000000000000000";
  const safe = {
    accountRef,
    profileState: "active",
    operations: {
      disable: { eligible: true, reason: null },
      reactivate: { eligible: false, reason: "already_active" },
      reassignDepartment: { eligible: false, reason: "role_not_reassignable" },
    },
  } as const;

  it("strictly parses only approved advisory fields", () => {
    expect(parseAdminLifecycleEligibility(safe)).toEqual(safe);
    expect(() => parseAdminLifecycleEligibility({ ...safe, uid: "private" })).toThrowError(AdminDirectoryError);
    expect(() => parseAdminLifecycleEligibility({ ...safe, operations: { ...safe.operations, disable: { eligible: true, reason: "private_reason" } } })).toThrowError(AdminDirectoryError);
  });

  it("uses a fresh token and local API for the read-only check", async () => {
    const getIdToken = vi.fn().mockResolvedValue("fresh-token");
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(safe), { status: 200 }));
    await loadAdminLifecycleEligibility(accountRef, fetcher);
    expect(getIdToken).toHaveBeenCalledWith(true);
    expect(fetcher.mock.calls[0][0]).toBe(`http://127.0.0.1:8000/admin/users/${accountRef}/lifecycle-eligibility`);
  });

  it("rejects malformed references before auth or fetch", async () => {
    const getIdToken = vi.fn();
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    const fetcher = vi.fn();
    await expect(loadAdminLifecycleEligibility("raw-uid", fetcher)).rejects.toMatchObject({ code: "validation" });
    expect(getIdToken).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
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
