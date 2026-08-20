export const LOCAL_EMULATOR_MODE = "local-emulator" as const;
export const CLOUD_STAGING_MODE = "cloud-staging" as const;

export type ApplicationMode = typeof LOCAL_EMULATOR_MODE | typeof CLOUD_STAGING_MODE;
export type RuntimeEnvironment = Record<string, string | undefined>;

export class RuntimeEnvironmentError extends Error {
  constructor(public readonly code: string) {
    super(code);
  }
}

type ResolvedMlApi = {
  mode: ApplicationMode;
  mlApiBaseUrl: string;
};

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]", "::1"]);

function requireMode(environment: RuntimeEnvironment): ApplicationMode {
  const mode = environment.NEXT_PUBLIC_APP_ENV;
  if (mode !== LOCAL_EMULATOR_MODE && mode !== CLOUD_STAGING_MODE) {
    throw new RuntimeEnvironmentError("application_environment_unsupported");
  }
  return mode;
}

function isLoopback(hostname: string): boolean {
  return LOOPBACK_HOSTS.has(hostname.toLowerCase());
}

export function resolveMlApiBaseUrl(
  environment: RuntimeEnvironment = process.env,
): ResolvedMlApi {
  const mode = requireMode(environment);
  if (mode === LOCAL_EMULATOR_MODE && environment.NODE_ENV === "production") {
    throw new RuntimeEnvironmentError("local_emulator_forbidden_in_production_build");
  }
  const rawUrl = environment.NEXT_PUBLIC_ML_API_URL;
  if (!rawUrl?.trim()) {
    throw new RuntimeEnvironmentError("ml_api_url_required");
  }

  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    throw new RuntimeEnvironmentError("ml_api_url_invalid");
  }
  if (parsed.username || parsed.password) {
    throw new RuntimeEnvironmentError("ml_api_url_credentials_forbidden");
  }
  if (parsed.pathname !== "/" || parsed.search || parsed.hash) {
    throw new RuntimeEnvironmentError("ml_api_url_base_only");
  }
  const loopback = isLoopback(parsed.hostname);
  if (mode === LOCAL_EMULATOR_MODE && !loopback) {
    throw new RuntimeEnvironmentError("local_ml_api_host_must_be_loopback");
  }
  if (mode === CLOUD_STAGING_MODE && (parsed.protocol !== "https:" || loopback)) {
    throw new RuntimeEnvironmentError("staging_ml_api_requires_https_non_loopback");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new RuntimeEnvironmentError("ml_api_url_protocol_invalid");
  }

  return { mode, mlApiBaseUrl: parsed.toString().replace(/\/$/u, "") };
}

export function resolveLocalMlApiBaseUrl(
  environment: RuntimeEnvironment = process.env,
): string {
  const resolved = resolveMlApiBaseUrl(environment);
  if (resolved.mode !== LOCAL_EMULATOR_MODE) {
    throw new RuntimeEnvironmentError("cloud_staging_not_adopted");
  }
  return resolved.mlApiBaseUrl;
}
