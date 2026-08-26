import type { FirebaseOptions } from "firebase/app";

import {
  CLOUD_STAGING_MODE,
  LOCAL_EMULATOR_MODE,
  type ApplicationMode,
  type RuntimeEnvironment,
} from "./runtime-environment";

export type FirebaseEnvironmentResult =
  | { mode: typeof LOCAL_EMULATOR_MODE; projectId: "demo-complaintguard" }
  | { mode: typeof CLOUD_STAGING_MODE; projectId: "complaintguard" };

export class FirebaseEnvironmentError extends Error {
  constructor(public readonly code: string) {
    super(code);
  }
}

const REQUIRED_PUBLIC_KEYS: (keyof FirebaseOptions)[] = [
  "apiKey",
  "authDomain",
  "projectId",
  "appId",
];
const CREDENTIAL_KEY_PATTERN = /(private|secret|token|credential|service.?account|refresh)/iu;
const CREDENTIAL_CONTENT_PATTERN = /BEGIN (?:[A-Z]+ )*PRIVATE KEY|private_key|client_email|service_account|refresh_token|access_token/iu;

function requireMode(environment: RuntimeEnvironment): ApplicationMode {
  const mode = environment.NEXT_PUBLIC_APP_ENV;
  if (mode !== LOCAL_EMULATOR_MODE && mode !== CLOUD_STAGING_MODE) {
    throw new FirebaseEnvironmentError("firebase_environment_unsupported");
  }
  return mode;
}

function rejectCredentialLikeConfiguration(environment: RuntimeEnvironment): void {
  for (const [key, value] of Object.entries(environment)) {
    if (!key.startsWith("NEXT_PUBLIC_")) continue;
    if (value && (CREDENTIAL_KEY_PATTERN.test(key) || CREDENTIAL_CONTENT_PATTERN.test(value))) {
      throw new FirebaseEnvironmentError("frontend_credential_configuration_forbidden");
    }
  }
  for (const key of ["NEXT_PUBLIC_FIREBASE_PRIVATE_KEY", "NEXT_PUBLIC_FIREBASE_CLIENT_SECRET"]) {
    if (environment[key]) throw new FirebaseEnvironmentError("frontend_credential_configuration_forbidden");
  }
}

function requirePublicConfig(options: FirebaseOptions): void {
  for (const [key, value] of Object.entries(options)) {
    if (typeof value === "string" && CREDENTIAL_CONTENT_PATTERN.test(value)) {
      throw new FirebaseEnvironmentError("frontend_credential_configuration_forbidden");
    }
    if (key !== "apiKey" && typeof value === "string" && CREDENTIAL_KEY_PATTERN.test(key)) {
      throw new FirebaseEnvironmentError("frontend_credential_configuration_forbidden");
    }
  }
  if (
    !REQUIRED_PUBLIC_KEYS.every((key) => {
      const value = options[key];
      return typeof value === "string" && value.length > 0 && !value.startsWith("replace_");
    })
  ) {
    throw new FirebaseEnvironmentError("firebase_public_config_incomplete");
  }
}

export function validateFirebaseEnvironment(
  environment: RuntimeEnvironment,
  options: FirebaseOptions,
): FirebaseEnvironmentResult {
  const mode = requireMode(environment);
  rejectCredentialLikeConfiguration(environment);
  requirePublicConfig(options);

  if (mode === LOCAL_EMULATOR_MODE) {
    if (environment.NODE_ENV === "production") {
      throw new FirebaseEnvironmentError("local_emulator_forbidden_in_production_build");
    }
    if (options.projectId !== "demo-complaintguard") {
      throw new FirebaseEnvironmentError("local_firebase_project_mismatch");
    }
    if (environment.NEXT_PUBLIC_USE_FIREBASE_EMULATORS !== "true") {
      throw new FirebaseEnvironmentError("local_emulators_must_be_enabled");
    }
    return { mode, projectId: "demo-complaintguard" };
  }

  if (options.projectId !== "complaintguard") {
    throw new FirebaseEnvironmentError("staging_firebase_project_mismatch");
  }
  if (environment.NEXT_PUBLIC_USE_FIREBASE_EMULATORS !== "false") {
    throw new FirebaseEnvironmentError("staging_emulators_must_be_disabled");
  }
  return { mode, projectId: "complaintguard" };
}
