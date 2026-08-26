import { describe, expect, it, vi } from "vitest";

import { getBrowserRuntimeEnvironment, resolveMlApiBaseUrl } from "./runtime-environment";

const local = {
  NEXT_PUBLIC_APP_ENV: "local-emulator",
  NEXT_PUBLIC_ML_API_URL: "http://127.0.0.1:8000/",
};

describe("runtime environment contract", () => {
  it("projects only approved browser runtime fields", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local-emulator");
    vi.stubEnv("NEXT_PUBLIC_USE_FIREBASE_EMULATORS", "true");
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://127.0.0.1:8000");
    vi.stubEnv("SECRET_NOT_FOR_BROWSER", "must-not-project");

    expect(getBrowserRuntimeEnvironment()).toEqual({
      NODE_ENV: "development",
      NEXT_PUBLIC_APP_ENV: "local-emulator",
      NEXT_PUBLIC_USE_FIREBASE_EMULATORS: "true",
      NEXT_PUBLIC_ML_API_URL: "http://127.0.0.1:8000",
    });
  });

  it("accepts and normalizes an explicit local API URL", () => {
    expect(resolveMlApiBaseUrl(local)).toEqual({
      mode: "local-emulator",
      mlApiBaseUrl: "http://127.0.0.1:8000",
    });
  });

  it.each([
    ["missing mode", { NEXT_PUBLIC_ML_API_URL: "http://127.0.0.1:8000" }],
    ["empty mode", { ...local, NEXT_PUBLIC_APP_ENV: "" }],
    ["unknown mode", { ...local, NEXT_PUBLIC_APP_ENV: "unknown" }],
    ["production mode", { ...local, NEXT_PUBLIC_APP_ENV: "production" }],
    ["missing URL", { NEXT_PUBLIC_APP_ENV: "local-emulator" }],
    ["non-loopback local URL", { ...local, NEXT_PUBLIC_ML_API_URL: "http://api.example.test" }],
    ["URL credentials", { ...local, NEXT_PUBLIC_ML_API_URL: "http://user:pass@127.0.0.1:8000" }],
    ["URL path", { ...local, NEXT_PUBLIC_ML_API_URL: "http://127.0.0.1:8000/api" }],
  ])("rejects %s", (_name, environment) => {
    expect(() => resolveMlApiBaseUrl(environment)).toThrow();
  });

  it("accepts a staging URL structurally without performing any request", () => {
    expect(
      resolveMlApiBaseUrl({
        NEXT_PUBLIC_APP_ENV: "cloud-staging",
        NEXT_PUBLIC_ML_API_URL: "https://api.example.test",
      }),
    ).toEqual({ mode: "cloud-staging", mlApiBaseUrl: "https://api.example.test" });
  });

  it.each([
    "http://api.example.test",
    "http://localhost:8000",
    "https://127.0.0.1:8000",
    "https://api.example.test/path",
  ])("rejects unsafe staging URL %s", (url) => {
    expect(() =>
      resolveMlApiBaseUrl({
        NEXT_PUBLIC_APP_ENV: "cloud-staging",
        NEXT_PUBLIC_ML_API_URL: url,
      }),
    ).toThrow();
  });
});
