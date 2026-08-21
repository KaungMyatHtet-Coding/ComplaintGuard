import { afterEach, describe, expect, it, vi } from "vitest";

import { getFirebaseServices, hasFirebaseConfig, shouldUseFirebaseEmulators } from "./firebase";

afterEach(() => vi.unstubAllEnvs());

describe("Firebase configuration boundary", () => {
  const localEnvironment = {
    NEXT_PUBLIC_APP_ENV: "local-emulator",
    NEXT_PUBLIC_USE_FIREBASE_EMULATORS: "true",
  };

  it("rejects missing and placeholder configuration", () => {
    expect(hasFirebaseConfig({})).toBe(false);
    expect(
      hasFirebaseConfig({
        apiKey: "replace_with_firebase_web_api_key",
        authDomain: "demo.firebaseapp.com",
        projectId: "demo",
        appId: "demo-app",
      }),
    ).toBe(false);
  });

  it("accepts a complete public web configuration", () => {
    expect(
      hasFirebaseConfig({
        apiKey: "synthetic-public-web-key",
        authDomain: "demo-complaintguard.firebaseapp.com",
        projectId: "demo-complaintguard",
        appId: "1:000:web:synthetic",
      }, localEnvironment),
    ).toBe(true);
  });

  it("uses the browser-safe environment projection for default validation", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local-emulator");
    vi.stubEnv("NEXT_PUBLIC_USE_FIREBASE_EMULATORS", "true");
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://127.0.0.1:8000");
    vi.stubEnv("SECRET_NOT_FOR_BROWSER", "must-not-be-required");

    expect(
      hasFirebaseConfig({
        apiKey: "synthetic-public-web-key",
        authDomain: "demo-complaintguard.firebaseapp.com",
        projectId: "demo-complaintguard",
        appId: "1:000:web:synthetic",
      }),
    ).toBe(true);
  });

  it("requires an explicit local development switch for emulators", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local-emulator");
    vi.stubEnv("NEXT_PUBLIC_USE_FIREBASE_EMULATORS", "true");
    expect(shouldUseFirebaseEmulators()).toBe(true);
  });

  it("refuses emulator connections in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local-emulator");
    vi.stubEnv("NEXT_PUBLIC_USE_FIREBASE_EMULATORS", "true");
    expect(shouldUseFirebaseEmulators()).toBe(false);
  });

  it("blocks candidate staging before Firebase service creation", () => {
    expect(() =>
      getFirebaseServices(
        {
          apiKey: "synthetic-public-web-key",
          authDomain: "complaintguard.firebaseapp.com",
          projectId: "complaintguard",
          appId: "1:000:web:synthetic",
        },
        {
          NEXT_PUBLIC_APP_ENV: "cloud-staging",
          NEXT_PUBLIC_USE_FIREBASE_EMULATORS: "false",
        },
      ),
    ).toThrow("cloud_staging_not_adopted");
  });
});
