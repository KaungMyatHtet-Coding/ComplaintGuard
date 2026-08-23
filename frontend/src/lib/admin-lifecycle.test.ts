import { beforeEach, describe, expect, it, vi } from "vitest";

const { getFirebaseServices } = vi.hoisted(() => ({ getFirebaseServices: vi.fn() }));
vi.mock("@/lib/firebase", () => ({ getFirebaseServices }));

import { AdminDirectoryError, parseAdminLifecycleEligibility } from "./admin-directory";
import {
  loadAdminLifecycleRecoveryStatus,
  parseAdminLifecycleRecoveryStatus,
} from "./admin-lifecycle";

const accountRef = "acct_v1_0000000000000000000000000000000000000000000000000000000000000000";

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local-emulator");
  vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://127.0.0.1:8000");
  getFirebaseServices.mockReset();
});

describe("parseAdminLifecycleRecoveryStatus", () => {
  const valid = [
    { accountRef, recoveryState: "none", operation: null, departmentId: null },
    { accountRef, recoveryState: "recoverable", operation: "disable", departmentId: null },
    { accountRef, recoveryState: "recoverable", operation: "reactivate", departmentId: null },
    { accountRef, recoveryState: "recoverable", operation: "reassign_department", departmentId: "card_atm" },
    { accountRef, recoveryState: "completed", operation: "disable", departmentId: null },
    { accountRef, recoveryState: "completed", operation: "reactivate", departmentId: null },
    { accountRef, recoveryState: "completed", operation: "reassign_department", departmentId: "fraud_security" },
    { accountRef, recoveryState: "operator_required", operation: null, departmentId: null },
  ] as const;

  it("accepts every approved strict union variant", () => {
    for (const value of valid) expect(parseAdminLifecycleRecoveryStatus(value)).toEqual(value);
  });

  it("rejects private, unknown, malformed, and invalid union fields", () => {
    const base = valid[0];
    const invalid = [
      { ...base, uid: "private" },
      { ...base, actionRef: "private" },
      { ...base, recoveryState: "running" },
      { ...base, operation: "delete" },
      { ...base, departmentId: "private" },
      { ...base, accountRef: "raw-uid" },
      { ...base, recoveryState: "none", operation: "disable" },
      { ...base, recoveryState: "operator_required", departmentId: "card_atm" },
      { ...base, recoveryState: "recoverable", operation: null },
      { ...base, recoveryState: "recoverable", operation: "disable", departmentId: "card_atm" },
      { ...base, recoveryState: "recoverable", operation: "reassign_department", departmentId: null },
      { ...base, recoveryState: "completed", operation: "reassign_department", departmentId: "unknown" },
      { ...base, operation: { value: "disable" } },
    ];
    for (const value of invalid) expect(() => parseAdminLifecycleRecoveryStatus(value)).toThrowError(AdminDirectoryError);
  });

  it("rejects inherited and non-enumerable private fields", () => {
    const inherited = Object.create({ actionRef: "private" });
    Object.assign(inherited, { accountRef, recoveryState: "none", operation: null, departmentId: null });
    expect(() => parseAdminLifecycleRecoveryStatus(inherited)).toThrowError(AdminDirectoryError);
    const hidden = { accountRef, recoveryState: "none", operation: null, departmentId: null };
    Object.defineProperty(hidden, "uid", { value: "private", enumerable: false });
    expect(() => parseAdminLifecycleRecoveryStatus(hidden)).toThrowError(AdminDirectoryError);
    const eligibility = {
      accountRef,
      profileState: "active",
      operations: {
        disable: { eligible: true, reason: null },
        reactivate: { eligible: false, reason: "already_active" },
        reassignDepartment: { eligible: false, reason: "role_not_reassignable" },
      },
    };
    const inheritedEligibility = Object.create({ uid: "private" });
    Object.assign(inheritedEligibility, eligibility);
    expect(() => parseAdminLifecycleEligibility(inheritedEligibility)).toThrowError(AdminDirectoryError);
    const hiddenEligibility = { ...eligibility } as Record<string, unknown>;
    Object.defineProperty(hiddenEligibility, "uid", { value: "private", enumerable: false });
    expect(() => parseAdminLifecycleEligibility(hiddenEligibility)).toThrowError(AdminDirectoryError);
  });
});

describe("loadAdminLifecycleRecoveryStatus", () => {
  it("retrieves a fresh token and uses the encoded read-only endpoint", async () => {
    const getIdToken = vi.fn().mockResolvedValue("fresh-token");
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      accountRef,
      recoveryState: "completed",
      operation: "disable",
      departmentId: null,
    }), { status: 200 }));
    const controller = new AbortController();
    await loadAdminLifecycleRecoveryStatus(accountRef, fetcher, controller.signal);
    expect(getIdToken).toHaveBeenCalledWith(true);
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`http://127.0.0.1:8000/admin/users/${accountRef}/lifecycle-recovery-status`);
    expect(init.method).toBe("GET");
    expect(init.signal).toBe(controller.signal);
    expect(init.headers).toEqual({ Authorization: "Bearer fresh-token" });
  });

  it("validates before token or fetch and maps safe failures", async () => {
    const getIdToken = vi.fn();
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    const fetcher = vi.fn();
    await expect(loadAdminLifecycleRecoveryStatus("raw-uid", fetcher)).rejects.toMatchObject({ code: "validation" });
    expect(getIdToken).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
    for (const [status, code] of [[401, "authentication"], [403, "permission"], [404, "notFound"], [422, "validation"], [503, "unavailable"]] as const) {
      getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken: vi.fn().mockResolvedValue("token") } } });
      const failing = vi.fn().mockResolvedValue(new Response("private", { status }));
      await expect(loadAdminLifecycleRecoveryStatus(accountRef, failing)).rejects.toMatchObject({ code });
    }
  });

  it("rejects a response bound to a different account", async () => {
    const getIdToken = vi.fn().mockResolvedValue("token");
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      accountRef: "acct_v1_1111111111111111111111111111111111111111111111111111111111111111",
      recoveryState: "none",
      operation: null,
      departmentId: null,
    }), { status: 200 }));
    await expect(loadAdminLifecycleRecoveryStatus(accountRef, fetcher)).rejects.toMatchObject({ code: "validation" });
  });
});
