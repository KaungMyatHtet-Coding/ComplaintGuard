import { beforeEach, describe, expect, it, vi } from "vitest";

const { getFirebaseServices } = vi.hoisted(() => ({ getFirebaseServices: vi.fn() }));
vi.mock("@/lib/firebase", () => ({ getFirebaseServices }));

import { AdminDirectoryError, parseAdminLifecycleEligibility } from "./admin-directory";
import {
  continueAdminDisable,
  continueAdminReactivate,
  disableAdminAccount,
  generateAdminLifecycleIdempotencyKey,
  loadAdminLifecycleRecoveryStatus,
  parseAdminDisableResult,
  parseAdminReactivateResult,
  reactivateAdminAccount,
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

describe("Admin disable mutation clients", () => {
  it("generates a cryptographic allowlisted key without persistence", () => {
    const getRandomValues = vi.fn((bytes: Uint8Array) => {
      bytes.fill(0);
      return bytes;
    });
    vi.stubGlobal("crypto", { getRandomValues });
    const key = generateAdminLifecycleIdempotencyKey();
    expect(key).toHaveLength(32);
    expect(key).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(getRandomValues).toHaveBeenCalledOnce();
  });

  it("posts a fresh disable with the exact safe request and response contract", async () => {
    const getIdToken = vi.fn().mockResolvedValue("fresh-token");
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      accountRef,
      operation: "disable",
      status: "completed",
      profileState: "inactive",
    }), { status: 200 }));
    await disableAdminAccount(accountRef, "A_secure-key_123", fetcher);
    expect(getIdToken).toHaveBeenCalledWith(true);
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`http://127.0.0.1:8000/admin/users/${accountRef}/disable`);
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ Authorization: "Bearer fresh-token", "Content-Type": "application/json" });
    expect(init.body).toBe(JSON.stringify({ idempotencyKey: "A_secure-key_123" }));
  });

  it("continues disable without accepting or sending an idempotency key", async () => {
    const getIdToken = vi.fn().mockResolvedValue("fresh-token");
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      accountRef,
      operation: "disable",
      status: "completed",
      profileState: "inactive",
    }), { status: 200 }));
    await continueAdminDisable(accountRef, fetcher);
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`http://127.0.0.1:8000/admin/users/${accountRef}/lifecycle-recovery`);
    expect(init.body).toBe(JSON.stringify({ operation: "disable" }));
  });

  it("rejects private or malformed disable results", () => {
    expect(() => parseAdminDisableResult({
      accountRef,
      operation: "disable",
      status: "completed",
      profileState: "inactive",
      actionRef: "private",
    })).toThrowError(AdminDirectoryError);
    const inherited = Object.create({ uid: "private" });
    Object.assign(inherited, { accountRef, operation: "disable", status: "completed", profileState: "inactive" });
    expect(() => parseAdminDisableResult(inherited)).toThrowError(AdminDirectoryError);
    const hidden = { accountRef, operation: "disable", status: "completed", profileState: "inactive" } as Record<string, unknown>;
    Object.defineProperty(hidden, "guardRef", { value: "private", enumerable: false });
    expect(() => parseAdminDisableResult(hidden)).toThrowError(AdminDirectoryError);
    const symbolField = { accountRef, operation: "disable", status: "completed", profileState: "inactive" } as Record<string | symbol, unknown>;
    symbolField[Symbol("private")] = "private";
    expect(() => parseAdminDisableResult(symbolField)).toThrowError(AdminDirectoryError);
  });

  it("rejects invalid keys before token or network access", async () => {
    const getIdToken = vi.fn();
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    const fetcher = vi.fn();
    await expect(disableAdminAccount(accountRef, "bad key", fetcher)).rejects.toMatchObject({ code: "validation" });
    expect(getIdToken).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("distinguishes unknown transport outcomes from safe HTTP errors", async () => {
    const getIdToken = vi.fn().mockResolvedValue("token");
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    await expect(disableAdminAccount(accountRef, "A_secure-key_123", vi.fn().mockRejectedValue(new Error("network"))))
      .rejects.toMatchObject({ code: "unavailable", outcome: "unknown" });
    await expect(disableAdminAccount(accountRef, "A_secure-key_123", vi.fn().mockRejectedValue(Object.assign(new Error("aborted"), { name: "AbortError" }))))
      .rejects.toMatchObject({ code: "unavailable", outcome: "unknown" });
    const conflict = vi.fn().mockResolvedValue(new Response("private", { status: 409 }));
    await expect(disableAdminAccount(accountRef, "A_secure-key_123", conflict))
      .rejects.toMatchObject({ code: "unexpected", outcome: "definitive", httpStatus: 409 });
  });
});

describe("Admin Reactivate mutation clients", () => {
  it("strictly parses the safe completed response and rejects hostile fields", () => {
    const valid = { accountRef, operation: "reactivate", status: "completed", profileState: "active" } as const;
    expect(parseAdminReactivateResult(valid)).toEqual(valid);
    expect(() => parseAdminReactivateResult({ ...valid, privateRef: "hidden" })).toThrowError(AdminDirectoryError);
    const inherited = Object.create({ uid: "private" });
    Object.assign(inherited, valid);
    expect(() => parseAdminReactivateResult(inherited)).toThrowError(AdminDirectoryError);
    const accessor = { ...valid } as Record<string, unknown>;
    Object.defineProperty(accessor, "privateRef", { get: () => "hidden", enumerable: true });
    expect(() => parseAdminReactivateResult(accessor)).toThrowError(AdminDirectoryError);
    const hidden = { ...valid } as Record<string, unknown>;
    Object.defineProperty(hidden, "privateRef", { value: "hidden", enumerable: false });
    expect(() => parseAdminReactivateResult(hidden)).toThrowError(AdminDirectoryError);
    const symbolField = { ...valid } as Record<string | symbol, unknown>;
    symbolField[Symbol("private")] = "hidden";
    expect(() => parseAdminReactivateResult(symbolField)).toThrowError(AdminDirectoryError);
    expect(() => parseAdminReactivateResult({ ...valid, operation: "disable" })).toThrowError(AdminDirectoryError);
    expect(() => parseAdminReactivateResult({ ...valid, profileState: "inactive" })).toThrowError(AdminDirectoryError);
    for (const hostile of [null, undefined, [], { ...valid, accountRef: 42 }, { ...valid, status: null }, { ...valid, profileState: {} }]) {
      expect(() => parseAdminReactivateResult(hostile)).toThrowError(AdminDirectoryError);
    }
    class ResponseLike {
      accountRef = accountRef;
      operation = "reactivate";
      status = "completed";
      profileState = "active";
    }
    expect(() => parseAdminReactivateResult(new ResponseLike())).toThrowError(AdminDirectoryError);
  });

  it("uses a fresh token, encoded account path, exact body, signal, and account binding", async () => {
    const getIdToken = vi.fn().mockResolvedValue("fresh-token");
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ accountRef, operation: "reactivate", status: "completed", profileState: "active" }), { status: 200 }));
    const controller = new AbortController();
    await reactivateAdminAccount(accountRef, "A_secure-key_123", fetcher, controller.signal);
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(getIdToken).toHaveBeenCalledWith(true);
    expect(url).toBe(`http://127.0.0.1:8000/admin/users/${encodeURIComponent(accountRef)}/reactivate`);
    expect(init.method).toBe("POST");
    expect(init.signal).toBe(controller.signal);
    expect(init.body).toBe(JSON.stringify({ idempotencyKey: "A_secure-key_123" }));
    expect(init.headers).toEqual({ Authorization: "Bearer fresh-token", "Content-Type": "application/json" });
    const wrongAccount = vi.fn().mockResolvedValue(new Response(JSON.stringify({ accountRef: `${accountRef.slice(0, -1)}1`, operation: "reactivate", status: "completed", profileState: "active" }), { status: 200 }));
    await expect(reactivateAdminAccount(accountRef, "A_secure-key_123", wrongAccount)).rejects.toMatchObject({ code: "validation", outcome: "unknown" });
  });

  it("continues recovery with exactly operation and no idempotency key", async () => {
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken: vi.fn().mockResolvedValue("fresh-token") } } });
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ accountRef, operation: "reactivate", status: "completed", profileState: "active" }), { status: 200 }));
    await continueAdminReactivate(accountRef, fetcher);
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`http://127.0.0.1:8000/admin/users/${accountRef}/lifecycle-recovery`);
    expect(init.body).toBe(JSON.stringify({ operation: "reactivate" }));
    expect(init.body).not.toContain("idempotencyKey");
  });
});
