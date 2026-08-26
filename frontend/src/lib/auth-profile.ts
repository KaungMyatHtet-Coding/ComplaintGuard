import { doc, getDoc, type Firestore } from "firebase/firestore";
import type { User } from "firebase/auth";

import { resolveUserProfile, type ProfileResolution, type UserProfile } from "./auth-policy";

export type ProfileLoadResult =
  | { kind: "valid"; profile: UserProfile }
  | Exclude<ProfileResolution, { kind: "valid" }>
  | { kind: "unavailable" };

export type ProfileDocumentSnapshot = {
  exists: () => boolean;
  data: () => Record<string, unknown> | undefined;
};

export type ProfileReader = (
  db: Firestore,
  uid: string,
) => Promise<ProfileDocumentSnapshot>;

const readProfile: ProfileReader = (db, uid) =>
  getDoc(doc(db, "users", uid)) as Promise<ProfileDocumentSnapshot>;

export async function loadAuthenticatedProfile(
  user: Pick<User, "uid" | "email">,
  db: Firestore,
  reader: ProfileReader = readProfile,
): Promise<ProfileLoadResult> {
  let snapshot;
  try {
    snapshot = await reader(db, user.uid);
  } catch {
    return { kind: "unavailable" };
  }
  const resolution = resolveUserProfile(
    user.uid,
    user.email ?? "",
    snapshot.exists(),
    snapshot.exists() ? snapshot.data() : null,
  );
  return resolution;
}
