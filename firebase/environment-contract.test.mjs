import assert from "node:assert/strict";
import test from "node:test";

import {
  EnvironmentSafetyError,
  validateLocalEmulatorEnvironment,
  validateLocalEmulatorMutation,
} from "./environment-contract.mjs";

const valid = Object.freeze({
  APP_ENV: "local-emulator",
  GCLOUD_PROJECT: "demo-complaintguard",
  FIREBASE_AUTH_EMULATOR_HOST: "127.0.0.1:9099",
  FIRESTORE_EMULATOR_HOST: "127.0.0.1:8185",
});

function assertRejected(environment, code) {
  assert.throws(
    () => validateLocalEmulatorEnvironment(environment),
    (error) => error instanceof EnvironmentSafetyError && (!code || error.message === code),
  );
}

test("accepts the complete local emulator contract", () => {
  assert.deepEqual(validateLocalEmulatorEnvironment(valid), {
    environment: "local-emulator",
    projectId: "demo-complaintguard",
    auth: { host: "127.0.0.1", port: 9099, authority: "127.0.0.1:9099" },
    firestore: { host: "127.0.0.1", port: 8185, authority: "127.0.0.1:8185" },
  });
});

test("rejects missing, unknown, staging, and production modes", () => {
  for (const mode of [undefined, "", "unknown", "cloud-staging", "staging", "production"]) {
    assertRejected({ ...valid, APP_ENV: mode }, "environment_mode_must_be_local_emulator");
  }
});

test("rejects missing, conflicting, candidate, and unknown projects", () => {
  assertRejected({ ...valid, GCLOUD_PROJECT: undefined }, "project_id_required");
  assertRejected({ ...valid, GCLOUD_PROJECT: "complaintguard" }, "project_id_must_be_demo_emulator");
  assertRejected({ ...valid, GCLOUD_PROJECT: "other-project" }, "project_id_must_be_demo_emulator");
  assertRejected({ ...valid, GOOGLE_CLOUD_PROJECT: "other-project" }, "project_id_conflict");
  assertRejected({ ...valid, GCLOUD_PROJECT: undefined, GOOGLE_CLOUD_PROJECT: undefined }, "project_id_required");
});

test("rejects missing, non-loopback, malformed, and unsafe hosts", () => {
  for (const environment of [
    { ...valid, FIREBASE_AUTH_EMULATOR_HOST: undefined },
    { ...valid, FIRESTORE_EMULATOR_HOST: undefined },
    { ...valid, FIREBASE_AUTH_EMULATOR_HOST: "192.168.1.10:9099" },
    { ...valid, FIRESTORE_EMULATOR_HOST: "8.8.8.8:8185" },
    { ...valid, FIREBASE_AUTH_EMULATOR_HOST: "http://127.0.0.1:9099" },
    { ...valid, FIRESTORE_EMULATOR_HOST: "user@127.0.0.1:8185" },
    { ...valid, FIRESTORE_EMULATOR_HOST: "127.0.0.1:8185/path" },
    { ...valid, FIRESTORE_EMULATOR_HOST: "127.0.0.1:8185?query=value" },
    { ...valid, FIRESTORE_EMULATOR_HOST: "127.0.0.1" },
    { ...valid, FIRESTORE_EMULATOR_HOST: "127.0.0.1:not-a-port" },
    { ...valid, FIRESTORE_EMULATOR_HOST: "127.0.0.1:0" },
    { ...valid, FIRESTORE_EMULATOR_HOST: "127.0.0.1:65536" },
  ]) {
    assertRejected(environment);
  }
});

test("accepts supported IPv6 loopback and rejects duplicate ports", () => {
  assert.equal(validateLocalEmulatorEnvironment({
    ...valid,
    FIREBASE_AUTH_EMULATOR_HOST: "[::1]:9099",
  }).auth.host, "::1");
  assertRejected({ ...valid, FIRESTORE_EMULATOR_HOST: "127.0.0.1:9099" }, "emulator_hosts_must_use_distinct_ports");
});

test("allows reset only after the complete local contract passes", () => {
  assert.equal(validateLocalEmulatorMutation(valid, { resetFirestore: true }).resetFirestore, true);
  assertRejected({ ...valid, GCLOUD_PROJECT: "complaintguard" }, "project_id_must_be_demo_emulator");
  assertRejected({ ...valid, APP_ENV: "cloud-staging" }, "environment_mode_must_be_local_emulator");
  assertRejected({ ...valid, FIRESTORE_EMULATOR_HOST: undefined }, "firestore_emulator_host_required");
});

test("rejects credential indicators without exposing their values", () => {
  for (const key of [
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_APPLICATION_CREDENTIALS_JSON",
    "FIREBASE_ADMIN_CREDENTIALS",
    "FIREBASE_SERVICE_ACCOUNT_JSON",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
  ]) {
    assertRejected({ ...valid, [key]: "sensitive-value" }, "cloud_credential_indicator_present");
  }
  assertRejected({ ...valid, FIREBASE_CONFIG: '{"private_key":"sensitive-value"}' }, "credential_json_in_firebase_config");
});
