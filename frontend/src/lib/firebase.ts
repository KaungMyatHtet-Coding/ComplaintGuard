import { getApp, getApps, initializeApp, type FirebaseOptions } from "firebase/app";
import { connectAuthEmulator, getAuth, type Auth } from "firebase/auth";
import {
  connectFirestoreEmulator,
  getFirestore,
  type Firestore,
} from "firebase/firestore";

import {
  FirebaseEnvironmentError,
  validateFirebaseEnvironment,
} from "./firebase-environment";
import {
  getBrowserRuntimeEnvironment,
  type RuntimeEnvironment,
} from "./runtime-environment";

const firebaseOptions: FirebaseOptions = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

export function hasFirebaseConfig(
  options = firebaseOptions,
  environment: RuntimeEnvironment = getBrowserRuntimeEnvironment(),
): boolean {
  try {
    validateFirebaseEnvironment(environment, options);
    return true;
  } catch {
    return false;
  }
}

export function getFirebaseServices(
  options = firebaseOptions,
  environmentValues: RuntimeEnvironment = getBrowserRuntimeEnvironment(),
): { auth: Auth; db: Firestore } {
  let environment;
  try {
    environment = validateFirebaseEnvironment(environmentValues, options);
  } catch (error) {
    if (error instanceof FirebaseEnvironmentError) throw new Error(error.code);
    throw new Error("firebase_configuration_missing");
  }
  if (environment.mode !== "local-emulator") {
    throw new Error("cloud_staging_not_adopted");
  }
  const app = getApps().length ? getApp() : initializeApp(options);
  if (app.options.projectId !== environment.projectId) {
    throw new Error("firebase_app_project_mismatch");
  }
  const auth = getAuth(app);
  const db = getFirestore(app);
  connectLocalEmulators(auth, db);
  return { auth, db };
}

let emulatorsConnected = false;

export function shouldUseFirebaseEmulators(): boolean {
  const environment = getBrowserRuntimeEnvironment();
  return (
    environment.NODE_ENV !== "production" &&
    environment.NEXT_PUBLIC_APP_ENV === "local-emulator" &&
    environment.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true"
  );
}

function connectLocalEmulators(auth: Auth, db: Firestore): void {
  if (!shouldUseFirebaseEmulators() || emulatorsConnected) return;
  connectAuthEmulator(auth, "http://127.0.0.1:9099", { disableWarnings: true });
  connectFirestoreEmulator(db, "127.0.0.1", 8185);
  emulatorsConnected = true;
}
