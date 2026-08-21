import { beforeEach, describe, expect, it, vi } from "vitest";

const { getFirebaseServices } = vi.hoisted(() => ({ getFirebaseServices: vi.fn() }));
vi.mock("@/lib/firebase", () => ({ getFirebaseServices }));

import {
  AdminProvisioningError,
  createIdempotencyKey,
  provisionAdminUser,
  validateAdminProvisioningForm,
} from "./admin-provisioning";

const environment = {
  NEXT_PUBLIC_APP_ENV: "local-emulator",
  NEXT_PUBLIC_ML_API_URL: "http://127.0.0.1:8000",
  NODE_ENV: "test",
};

const validStaff = {
  email: " staff@example.test ",
  displayName: "  Synthetic   Staff ",
  locale: "my",
  role: "staff",
  departmentId: "card_atm",
};

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_APP_ENV", environment.NEXT_PUBLIC_APP_ENV);
  vi.stubEnv("NEXT_PUBLIC_ML_API_URL", environment.NEXT_PUBLIC_ML_API_URL);
  vi.stubEnv("NODE_ENV", environment.NODE_ENV);
  getFirebaseServices.mockReset();
});

describe("validateAdminProvisioningForm", () => {
  it("normalizes valid Staff input", () => {
    expect(validateAdminProvisioningForm(validStaff)).toEqual({
      email: "staff@example.test",
      displayName: "Synthetic Staff",
      locale: "my",
      role: "staff",
      departmentId: "card_atm",
    });
  });

  it("requires a department for Staff and omits it for Manager", () => {
    expect(() => validateAdminProvisioningForm({ ...validStaff, departmentId: null })).toThrow();
    expect(validateAdminProvisioningForm({ ...validStaff, role: "manager", departmentId: null })).toMatchObject({
      role: "manager",
      departmentId: null,
    });
  });

  it("rejects roles, fields, and values outside the public Admin contract", () => {
    for (const role of ["customer", "admin", "custom"]) {
      expect(() => validateAdminProvisioningForm({ ...validStaff, role })).toThrow();
    }
    for (const field of ["uid", "password", "active", "claims", "actorRole"]) {
      expect(() => validateAdminProvisioningForm({ ...validStaff, [field]: "blocked" })).toThrow();
    }
    expect(() => validateAdminProvisioningForm({ ...validStaff, locale: "fr" })).toThrow();
    expect(() => validateAdminProvisioningForm({ ...validStaff, departmentId: "unknown" })).toThrow();
  });
});

describe("provisionAdminUser", () => {
  it("uses a fresh token and sends only the approved Staff fields", async () => {
    const getIdToken = vi.fn().mockResolvedValue("fresh-token");
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "pending_setup",
        email: "staff@example.test",
        displayName: "Synthetic Staff",
        locale: "my",
        role: "staff",
        departmentId: "card_atm",
        active: false,
        setupRequired: true,
      }), { status: 201, headers: { "Content-Type": "application/json" } }),
    );

    await provisionAdminUser({ ...validStaff, idempotencyKey: "key-123456" }, fetcher);

    expect(getIdToken).toHaveBeenCalledWith(true);
    const request = fetcher.mock.calls[0][1] as RequestInit;
    expect(fetcher.mock.calls[0][0]).toBe("http://127.0.0.1:8000/admin/users");
    expect(request.method).toBe("POST");
    expect(JSON.parse(String(request.body))).toEqual({
      email: "staff@example.test",
      displayName: "Synthetic Staff",
      locale: "my",
      role: "staff",
      departmentId: "card_atm",
      idempotencyKey: "key-123456",
    });
  });

  it("omits Manager department and maps safe backend errors", async () => {
    const getIdToken = vi.fn().mockResolvedValue("fresh-token");
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "email_exists" }), { status: 409 }));
    await expect(provisionAdminUser({ ...validStaff, role: "manager", departmentId: null, idempotencyKey: "key-123456" }, fetcher)).rejects.toMatchObject({ code: "email_exists" });
    expect(JSON.parse(String((fetcher.mock.calls[0][1] as RequestInit).body))).not.toHaveProperty("departmentId");
  });

  it("does not obtain a token or fetch when environment validation fails", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "cloud-staging");
    const getIdToken = vi.fn();
    getFirebaseServices.mockReturnValue({ auth: { currentUser: { getIdToken } } });
    const fetcher = vi.fn();
    await expect(provisionAdminUser({ ...validStaff, idempotencyKey: "key-123456" }, fetcher)).rejects.toMatchObject({ code: "unavailable" });
    expect(getIdToken).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("requires a current authenticated user", async () => {
    getFirebaseServices.mockReturnValue({ auth: { currentUser: null } });
    await expect(provisionAdminUser({ ...validStaff, idempotencyKey: "key-123456" }, vi.fn())).rejects.toMatchObject({ code: "authentication" });
  });

  it("generates a browser-random idempotency key without exposing its value", () => {
    vi.stubGlobal("crypto", { randomUUID: () => "12345678-1234-4234-8234-123456789abc" });
    const key = createIdempotencyKey();
    expect(key).toMatch(/^[0-9a-f-]{36}$/u);
    expect(new AdminProvisioningError("unexpected").message).toBe("unexpected");
  });
});
