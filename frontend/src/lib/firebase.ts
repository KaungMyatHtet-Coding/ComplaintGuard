import { getApp, getApps, initializeApp, type FirebaseOptions } from "firebase/app";
import { connectAuthEmulator, getAuth, type Auth } from "firebase/auth";
import {
  connectFirestoreEmulator,
  getFirestore,
  type Firestore,
} from "firebase/firestore";

const firebaseOptions: FirebaseOptions = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

const requiredKeys: (keyof FirebaseOptions)[] = [
  "apiKey",
  "authDomain",
  "projectId",
  "appId",
];

export function hasFirebaseConfig(options = firebaseOptions): boolean {
  return requiredKeys.every((key) => {
    const value = options[key];
    return typeof value === "string" && value.length > 0 && !value.startsWith("replace_");
  });
}

export function getFirebaseServices(): { auth: Auth; db: Firestore } {
  if (!hasFirebaseConfig()) {
    throw new Error("firebase_configuration_missing");
  }
  const app = getApps().length ? getApp() : initializeApp(firebaseOptions);
  const auth = getAuth(app);
  const db = getFirestore(app);
  connectLocalEmulators(auth, db);
  return { auth, db };
}

let emulatorsConnected = false;

export function shouldUseFirebaseEmulators(): boolean {
  return (
    process.env.NODE_ENV !== "production" &&
    process.env.NEXT_PUBLIC_APP_ENV === "local-emulator" &&
    process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true"
  );
}

function connectLocalEmulators(auth: Auth, db: Firestore): void {
  if (!shouldUseFirebaseEmulators() || emulatorsConnected) return;
  connectAuthEmulator(auth, "http://127.0.0.1:9099", { disableWarnings: true });
  connectFirestoreEmulator(db, "127.0.0.1", 8185);
  emulatorsConnected = true;
}
