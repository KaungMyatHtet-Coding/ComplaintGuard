import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { User } from "firebase/auth";

import {
  completeCustomerProfile,
  CustomerProfileError,
  validateCustomerProfileInput,
} from "./customer-profile";

const originalEnvironment = {
  app: process.env.NEXT_PUBLIC_APP_ENV,
  api: process.env.NEXT_PUBLIC_ML_API_URL,
};

function fakeUser(getIdToken = vi.fn().mockResolvedValue("fresh-token")) {
  return {
    uid: "uid-customer",
    email: "customer@example.test",
    getIdToken,
  } as unknown as User;
}

function response(body: unknown, status = 201) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const completionBody = {
  status: "created",
  profile: {
    uid: "uid-customer",
    email: "customer@example.test",
    displayName: "Synthetic Customer",
    locale: "my",
    role: "customer",
    departmentId: null,
    active: true,
  },
};

describe("Customer profile completion client", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local-emulator");
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://127.0.0.1:8000");
  });

  afterEach(() => {
    if (originalEnvironment.app === undefined) delete process.env.NEXT_PUBLIC_APP_ENV;
    else process.env.NEXT_PUBLIC_APP_ENV = originalEnvironment.app;
    if (originalEnvironment.api === undefined) delete process.env.NEXT_PUBLIC_ML_API_URL;
    else process.env.NEXT_PUBLIC_ML_API_URL = originalEnvironment.api;
    vi.unstubAllEnvs();
  });

  it("normalizes only approved request fields", () => {
    expect(
      validateCustomerProfileInput({
        displayName: "  Synthetic   Customer ",
        locale: "my",
        termsAccepted: true,
      }),
    ).toEqual({
      displayName: "Synthetic Customer",
      locale: "my",
      termsAccepted: true,
    });
    expect(() =>
      validateCustomerProfileInput({
        displayName: "Customer",
        locale: "en",
        role: "admin",
      }),
    ).toThrowError(new CustomerProfileError("invalid_input"));
  });

  it("requires an authenticated user before token or fetch", async () => {
    const fetcher = vi.fn();
    await expect(
      completeCustomerProfile(null, { displayName: "Customer", locale: "en" }, fetcher),
    ).rejects.toMatchObject({ code: "not_authenticated" });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("validates before obtaining a token or making a request", async () => {
    const getIdToken = vi.fn();
    const fetcher = vi.fn();
    await expect(
      completeCustomerProfile(
        fakeUser(getIdToken),
        { displayName: "Customer", locale: "en", uid: "injected" },
        fetcher,
      ),
    ).rejects.toMatchObject({ code: "invalid_input" });
    expect(getIdToken).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("uses a fresh ID token and sends only approved fields", async () => {
    const getIdToken = vi.fn().mockResolvedValue("fresh-token");
    const fetcher = vi.fn().mockResolvedValue(response(completionBody));

    await expect(
      completeCustomerProfile(
        fakeUser(getIdToken),
        { displayName: "Synthetic Customer", locale: "my", termsAccepted: true },
        fetcher,
      ),
    ).resolves.toEqual(completionBody);
    expect(getIdToken).toHaveBeenCalledWith(true);
    const request = fetcher.mock.calls[0][1] as RequestInit;
    expect(request.headers).toEqual({
      Authorization: "Bearer fresh-token",
      "Content-Type": "application/json",
    });
    expect(JSON.parse(String(request.body))).toEqual({
      displayName: "Synthetic Customer",
      locale: "my",
      termsAccepted: true,
    });
  });

  it("handles an existing-profile response safely", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      response({ ...completionBody, status: "existing" }, 200),
    );
    await expect(
      completeCustomerProfile(fakeUser(), { displayName: "Customer", locale: "en" }, fetcher),
    ).resolves.toMatchObject({ status: "existing", profile: { role: "customer" } });
  });

  it.each([
    [401, "auth"],
    [409, "conflict"],
    [422, "validation"],
    [503, "unavailable"],
  ] as const)("maps HTTP %s to a safe state", async (status, code) => {
    const fetcher = vi.fn().mockResolvedValue(response({}, status));
    await expect(
      completeCustomerProfile(fakeUser(), { displayName: "Customer", locale: "en" }, fetcher),
    ).rejects.toMatchObject({ code });
  });

  it("maps network and unexpected responses without exposing internals", async () => {
    const network = vi.fn().mockRejectedValue(new Error("internal failure"));
    await expect(
      completeCustomerProfile(fakeUser(), { displayName: "Customer", locale: "en" }, network),
    ).rejects.toMatchObject({ code: "unavailable" });

    const unexpected = vi.fn().mockResolvedValue(response({ internal: "details" }, 200));
    await expect(
      completeCustomerProfile(fakeUser(), { displayName: "Customer", locale: "en" }, unexpected),
    ).rejects.toMatchObject({ code: "unexpected" });
  });

  it("blocks invalid environments before fetch", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "cloud-staging");
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "https://api.example.test");
    const fetcher = vi.fn();
    await expect(
      completeCustomerProfile(fakeUser(), { displayName: "Customer", locale: "en" }, fetcher),
    ).rejects.toMatchObject({ code: "environment" });
    expect(fetcher).not.toHaveBeenCalled();
  });
});
