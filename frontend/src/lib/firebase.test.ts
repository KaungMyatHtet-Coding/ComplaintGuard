import { describe, expect, it } from "vitest";

import { hasFirebaseConfig } from "./firebase";

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
});
