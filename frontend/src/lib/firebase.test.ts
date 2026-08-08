import { afterEach, describe, expect, it, vi } from "vitest";

import { hasFirebaseConfig, shouldUseFirebaseEmulators } from "./firebase";

afterEach(() => vi.unstubAllEnvs());

describe("Firebase configuration boundary", () => {
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
        authDomain: "synthetic-project.firebaseapp.com",
        projectId: "synthetic-project",
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
});
