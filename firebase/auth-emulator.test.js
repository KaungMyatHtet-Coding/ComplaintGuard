import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { deleteApp, initializeApp } from "firebase/app";
import {
  connectAuthEmulator,
  getAuth,
  signInWithEmailAndPassword,
  signOut,
} from "firebase/auth";
import { connectFirestoreEmulator, doc, getDoc, getFirestore } from "firebase/firestore";
import { describe, expect, it } from "vitest";

describe("ComplaintGuard Auth Emulator identities", () => {
  it("authenticates every seeded role and reads only its trusted profile", async () => {
    const seed = JSON.parse(
      await readFile(resolve(".firebase", "seeded-identities.json"), "utf8"),
    );
    for (const identity of seed.identities) {
      const app = initializeApp(
        { apiKey: "emulator-only", projectId: seed.projectId },
        `auth-test-${identity.key}`,
      );
      const auth = getAuth(app);
      connectAuthEmulator(auth, "http://127.0.0.1:9099", { disableWarnings: true });
      const db = getFirestore(app);
      connectFirestoreEmulator(db, "127.0.0.1", 8185);
      const credential = await signInWithEmailAndPassword(
        auth,
        identity.email,
        identity.password,
      );
      expect(credential.user.uid).toBe(identity.uid);
      const profile = await getDoc(doc(db, "users", identity.uid));
      expect(profile.exists()).toBe(true);
      expect(profile.data().role).toBe(identity.role);
      await signOut(auth);
      expect(auth.currentUser).toBeNull();
      await deleteApp(app);
    }
  });
});
