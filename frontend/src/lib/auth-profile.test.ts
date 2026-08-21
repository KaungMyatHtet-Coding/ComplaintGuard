import { describe, expect, it } from "vitest";

import { loadAuthenticatedProfile, type ProfileReader } from "./auth-profile";

const user = { uid: "uid-customer", email: "customer@example.test" };
const db = {} as never;

function snapshot(data: Record<string, unknown> | null, exists = data !== null) {
  return {
    exists: () => exists,
    data: () => data ?? undefined,
  };
}

function profile(overrides: Record<string, unknown> = {}) {
  return {
    email: user.email,
    displayName: "Synthetic Customer",
    locale: "en",
    role: "customer",
    departmentId: null,
    active: true,
    createdAt: "synthetic-created",
    updatedAt: "synthetic-updated",
    ...overrides,
  };
}

function readerFor(result: ReturnType<typeof snapshot>): ProfileReader {
  return async () => result;
}

describe("authenticated profile loading", () => {
  it("classifies a definitely missing document as recoverable", async () => {
    await expect(
      loadAuthenticatedProfile(user, db, readerFor(snapshot(null, false))),
    ).resolves.toEqual({ kind: "missing" });
  });

  it.each(["customer", "staff", "manager", "admin"])(
    "authenticates a valid %s profile normally",
    async (role) => {
      await expect(
        loadAuthenticatedProfile(
          user,
          db,
          readerFor(
            snapshot(
              profile({
                role,
                departmentId: role === "staff" ? "card_atm" : null,
              }),
            ),
          ),
        ),
      ).resolves.toMatchObject({ kind: "valid", profile: { role } });
    },
  );

  it("does not classify an inactive profile as recoverable", async () => {
    await expect(
      loadAuthenticatedProfile(user, db, readerFor(snapshot(profile({ active: false })))),
    ).resolves.toEqual({ kind: "inactive" });
  });

  it("does not classify malformed data as recoverable", async () => {
    await expect(
      loadAuthenticatedProfile(
        user,
        db,
        readerFor(snapshot(profile({ departmentId: "not-a-department" }))),
      ),
    ).resolves.toEqual({ kind: "malformed" });
  });

  it("keeps Firestore failures separate from missing profiles", async () => {
    const failingReader: ProfileReader = async () => {
      throw new Error("network unavailable");
    };
    await expect(loadAuthenticatedProfile(user, db, failingReader)).resolves.toEqual({
      kind: "unavailable",
    });
  });
});
