export const LOCAL_EMULATOR_ENVIRONMENT = "local-emulator";
export const DEMO_PROJECT_ID = "demo-complaintguard";

const CREDENTIAL_INDICATOR_KEYS = Object.freeze([
  "GOOGLE_APPLICATION_CREDENTIALS",
  "GOOGLE_APPLICATION_CREDENTIALS_JSON",
  "FIREBASE_ADMIN_CREDENTIALS",
  "FIREBASE_ADMIN_CREDENTIALS_JSON",
  "FIREBASE_SERVICE_ACCOUNT_JSON",
  "GOOGLE_SERVICE_ACCOUNT_JSON",
]);

export class EnvironmentSafetyError extends Error {
  constructor(code) {
    super(code);
    this.name = "EnvironmentSafetyError";
  }
}

export function validateLocalEmulatorEnvironment(environment = process.env) {
  if (environment.APP_ENV !== LOCAL_EMULATOR_ENVIRONMENT) {
    throw new EnvironmentSafetyError("environment_mode_must_be_local_emulator");
  }

  const projectValues = [environment.GCLOUD_PROJECT, environment.GOOGLE_CLOUD_PROJECT]
    .filter((value) => typeof value === "string" && value.trim());
  if (!projectValues.length) {
    throw new EnvironmentSafetyError("project_id_required");
  }
  if (new Set(projectValues).size !== 1) {
    throw new EnvironmentSafetyError("project_id_conflict");
  }
  if (projectValues[0] !== DEMO_PROJECT_ID) {
    throw new EnvironmentSafetyError("project_id_must_be_demo_emulator");
  }

  assertNoCredentialIndicators(environment);
  const auth = parseLoopbackEmulatorHost(environment.FIREBASE_AUTH_EMULATOR_HOST, "auth");
  const firestore = parseLoopbackEmulatorHost(environment.FIRESTORE_EMULATOR_HOST, "firestore");
  if (auth.port === firestore.port) {
    throw new EnvironmentSafetyError("emulator_hosts_must_use_distinct_ports");
  }

  return Object.freeze({
    environment: LOCAL_EMULATOR_ENVIRONMENT,
    projectId: DEMO_PROJECT_ID,
    auth,
    firestore,
  });
}

export function validateLocalEmulatorMutation(
  environment = process.env,
  { resetFirestore = false } = {},
) {
  const validated = validateLocalEmulatorEnvironment(environment);
  if (typeof resetFirestore !== "boolean") {
    throw new EnvironmentSafetyError("reset_option_invalid");
  }
  return Object.freeze({ ...validated, resetFirestore });
}

export function parseLoopbackEmulatorHost(value, name) {
  if (typeof value !== "string" || !value || value !== value.trim()) {
    throw new EnvironmentSafetyError(`${name}_emulator_host_required`);
  }
  const match = /^(?<host>127\.0\.0\.1|localhost):(?<port>\d{1,5})$/u.exec(value)
    ?? /^\[(?<host>::1)\]:(?<port>\d{1,5})$/u.exec(value);
  if (!match?.groups) {
    throw new EnvironmentSafetyError(`${name}_emulator_host_must_be_loopback`);
  }
  const port = Number(match.groups.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new EnvironmentSafetyError(`${name}_emulator_port_invalid`);
  }
  return Object.freeze({
    host: match.groups.host,
    port,
    authority: value,
  });
}

export function assertNoCredentialIndicators(environment = process.env) {
  for (const key of CREDENTIAL_INDICATOR_KEYS) {
    if (typeof environment[key] === "string" && environment[key].trim()) {
      throw new EnvironmentSafetyError("cloud_credential_indicator_present");
    }
  }

  const firebaseConfig = environment.FIREBASE_CONFIG;
  if (typeof firebaseConfig === "string" && /private[_-]?key|client[_-]?email|credential/iu.test(firebaseConfig)) {
    throw new EnvironmentSafetyError("credential_json_in_firebase_config");
  }
}
