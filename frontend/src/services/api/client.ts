/**
 * Typed REST client, per ARCHITECTURE.md section 5. No endpoints are
 * wired yet -- this is the shared request/response/error envelope
 * handling every future `services/api/<feature>.ts` module will call
 * into, not a per-feature client.
 */

const API_BASE_URL = "http://127.0.0.1:8000/api/v1";

export interface ApiErrorPayload {
  code: string;
  message: string;
  recovery_action: string | null;
  severity: "info" | "warning" | "error" | "critical";
  retryable: boolean;
}

export class ApiError extends Error {
  readonly code: string;
  readonly recoveryAction: string | null;
  readonly severity: ApiErrorPayload["severity"];
  readonly retryable: boolean;

  constructor(payload: ApiErrorPayload) {
    super(payload.message);
    this.name = "ApiError";
    this.code = payload.code;
    this.recoveryAction = payload.recovery_action;
    this.severity = payload.severity;
    this.retryable = payload.retryable;
  }
}

interface ApiEnvelope<T> {
  data: T;
  meta?: { next_cursor?: string | null; [key: string]: unknown };
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

let authToken: string | null = null;

/** Set by the auth flow once it exists (M9/M14) -- never read from
 *  anywhere else, matching ARCHITECTURE.md section 5's single Bearer
 *  auth mechanism. */
export function setAuthToken(token: string | null): void {
  authToken = token;
}

/**
 * The one function every typed endpoint helper calls through. Throws
 * `ApiError` on any non-2xx response, using the server's own error
 * envelope (section 5/9) rather than a generic HTTP status message.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    signal: options.signal,
    headers: {
      "Content-Type": "application/json",
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    },
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  const json = (await response.json().catch(() => null)) as
    | ApiEnvelope<T>
    | { error: ApiErrorPayload }
    | null;

  if (!response.ok) {
    if (json && "error" in json) {
      throw new ApiError(json.error);
    }
    throw new ApiError({
      code: "UNKNOWN_ERROR",
      message: `Request to ${path} failed with status ${response.status}.`,
      recovery_action: null,
      severity: "error",
      retryable: response.status >= 500,
    });
  }

  return (json as ApiEnvelope<T>).data;
}
