import { describe, expect, it } from "vitest";

import { validateFirebaseEnvironment } from "./firebase-environment";

const publicConfig = {
  apiKey: "synthetic-public-web-key",
  authDomain: "demo-complaintguard.firebaseapp.com",
  projectId: "demo-complaintguard",
  appId: "1:000:web:synthetic",
};

const local = {
  NEXT_PUBLIC_APP_ENV: "local-emulator",
  NEXT_PUBLIC_USE_FIREBASE_EMULATORS: "true",
};

describe("Firebase environment contract", () => {
  it("accepts the exact local emulator contract", () => {
    expect(validateFirebaseEnvironment(local, publicConfig)).toEqual({
      mode: "local-emulator",
      projectId: "demo-complaintguard",
    });
  });

  it.each([
    ["wrong project", { ...publicConfig, projectId: "complaintguard" }, local],
    ["missing emulator flag", publicConfig, { NEXT_PUBLIC_APP_ENV: "local-emulator" }],
    ["disabled emulator flag", publicConfig, { ...local, NEXT_PUBLIC_USE_FIREBASE_EMULATORS: "false" }],
    ["incomplete public config", { ...publicConfig, appId: "" }, local],
    ["private credential content", publicConfig, { ...local, NEXT_PUBLIC_FIREBASE_CONFIG_JSON: '{"private_key":"x"}' }],
    ["private key content in public field", publicConfig, { ...local, NEXT_PUBLIC_FIREBASE_API_KEY: "-----BEGIN PRIVATE KEY-----" }],
    ["production build local mode", publicConfig, { ...local, NODE_ENV: "production" }],
    ["unsupported mode", publicConfig, { ...local, NEXT_PUBLIC_APP_ENV: "production" }],
  ])("rejects %s", (_name, options, environment) => {
    expect(() => validateFirebaseEnvironment(environment, options)).toThrow();
  });

  it("recognizes staging structurally without adopting it", () => {
    expect(
      validateFirebaseEnvironment(
        {
          NEXT_PUBLIC_APP_ENV: "cloud-staging",
          NEXT_PUBLIC_USE_FIREBASE_EMULATORS: "false",
        },
        { ...publicConfig, authDomain: "complaintguard.firebaseapp.com", projectId: "complaintguard" },
      ),
    ).toEqual({ mode: "cloud-staging", projectId: "complaintguard" });
  });

  it.each([
    { NEXT_PUBLIC_APP_ENV: "cloud-staging", NEXT_PUBLIC_USE_FIREBASE_EMULATORS: "true" },
    { NEXT_PUBLIC_APP_ENV: "cloud-staging" },
    { NEXT_PUBLIC_APP_ENV: "cloud-staging", NEXT_PUBLIC_USE_FIREBASE_EMULATORS: "false", NEXT_PUBLIC_FIREBASE_PRIVATE_KEY: "not-a-secret" },
  ])("rejects invalid staging configuration", (environment) => {
    expect(() =>
      validateFirebaseEnvironment(
        environment,
        { ...publicConfig, projectId: "complaintguard" },
      ),
    ).toThrow();
  });
});
