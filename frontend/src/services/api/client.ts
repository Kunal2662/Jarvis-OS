/**
 * The typed REST client -- M8 Phase 2.
 *
 * Phase 1 shipped this file as envelope handling with "no endpoints
 * wired yet". Phase 2 wires it to the real backend, and in doing so
 * corrects two places where the client had drifted from what the server
 * actually sends:
 *
 * 1. **Pagination.** This file expected `meta.next_cursor`, matching
 *    `ARCHITECTURE.md` section 5's *specified* cursor scheme. The backend
 *    ships offset paging -- `meta: {count, limit, offset, has_more}` --
 *    as of M11 Task Group F, which recorded that divergence in the
 *    architecture doc rather than hiding it. The client follows what the
 *    server sends, not what the spec wished for.
 * 2. **Error envelope.** Every FastAPI route in this application raises
 *    `HTTPException`, which serialises as `{"detail": "..."}`. This file
 *    only understood the richer `{"error": {code, message, ...}}` shape
 *    from section 9, which no route actually produces, so every failure
 *    fell through to a generic "failed with status N" and threw away the
 *    server's actual reason. Both shapes are handled now, `detail` first
 *    because it is the one that occurs.
 *
 * The base URL is configurable because Tauri and `vite dev` reach the
 * Python process differently, and hardcoding one breaks the other.
 */

export interface ApiErrorPayload {
  code: string;
  message: string;
  recovery_action: string | null;
  severity: "info" | "warning" | "error" | "critical";
  retryable: boolean;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly recoveryAction: string | null;
  readonly severity: ApiErrorPayload["severity"];
  readonly retryable: boolean;

  constructor(payload: ApiErrorPayload, status: number, options?: { cause?: unknown }) {
    super(payload.message, options);
    this.name = "ApiError";
    this.code = payload.code;
    this.status = status;
    this.recoveryAction = payload.recovery_action;
    this.severity = payload.severity;
    this.retryable = payload.retryable;
  }

  /** A request that never reached the server. Distinct from a 5xx: the
   *  backend is not merely unhappy, it is unreachable, which is what
   *  drives the app's offline state rather than an error toast. */
  get isOffline(): boolean {
    return this.code === "BACKEND_UNREACHABLE";
  }
}

/** `meta` for a paginated collection, exactly as the backend's
 *  `infrastructure/api/pagination.py` builds it. */
export interface PageMeta {
  count: number;
  limit: number;
  offset: number;
  has_more: boolean;
  [key: string]: unknown;
}

/** A page of results plus the cursor-free bookkeeping needed to ask for
 *  the next one. Returned by `apiList`; `apiRequest` unwraps to `data`
 *  alone for the single-resource case. */
export interface Page<T> {
  items: T[];
  meta: PageMeta;
}

export interface ApiEnvelope<T> {
  data: T;
  meta?: Record<string, unknown>;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  /** Skip the Authorization header. Only `POST /sessions` needs this --
   *  it is the call that *obtains* the token. */
  anonymous?: boolean;
}

const DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1";

let baseUrl: string = readConfiguredBaseUrl();
let authToken: string | null = null;

function readConfiguredBaseUrl(): string {
  // `import.meta.env` is replaced at build time by Vite; the fallback
  // keeps this module usable under vitest/node where it is undefined.
  const configured = (import.meta.env?.VITE_API_BASE_URL as string | undefined) ?? "";
  return configured.trim() || DEFAULT_BASE_URL;
}

export function getApiBaseUrl(): string {
  return baseUrl;
}

/** Point the client at a different backend. Used by the Tauri shell and
 *  by tests; not something a feature module should call. */
export function setApiBaseUrl(url: string): void {
  baseUrl = url.replace(/\/$/, "");
}

/**
 * Set by the session flow (`services/api/session.ts`) and read nowhere
 * else, matching `ARCHITECTURE.md` section 5's single Bearer mechanism.
 */
export function setAuthToken(token: string | null): void {
  authToken = token;
}

export function getAuthToken(): string | null {
  return authToken;
}

function buildUrl(path: string, query: RequestOptions["query"]): string {
  const url = `${baseUrl}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null) continue;
    params.set(key, String(value));
  }
  const serialised = params.toString();
  return serialised ? `${url}?${serialised}` : url;
}

function toApiError(status: number, body: unknown): ApiError {
  // FastAPI's own shape, which is what every route in this application
  // actually raises.
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    return new ApiError(
      {
        code: status === 401 ? "UNAUTHENTICATED" : `HTTP_${status}`,
        message: typeof detail === "string" ? detail : JSON.stringify(detail),
        recovery_action: status === 401 ? "Sign in again." : null,
        severity: status >= 500 ? "error" : "warning",
        retryable: status >= 500 || status === 429,
      },
      status,
    );
  }
  // The richer envelope ARCHITECTURE.md section 9 specifies, for
  // whenever a route starts emitting it.
  if (body && typeof body === "object" && "error" in body) {
    return new ApiError((body as { error: ApiErrorPayload }).error, status);
  }
  return new ApiError(
    {
      code: `HTTP_${status}`,
      message: `Request failed with status ${status}.`,
      recovery_action: null,
      severity: "error",
      retryable: status >= 500,
    },
    status,
  );
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  try {
    return await fetch(buildUrl(path, options.query), {
      method: options.method ?? "GET",
      signal: options.signal,
      headers: {
        "Content-Type": "application/json",
        ...(authToken && !options.anonymous ? { Authorization: `Bearer ${authToken}` } : {}),
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch (cause) {
    // `fetch` rejects only when the request never completed -- DNS,
    // refused connection, the Python process not running. That is the
    // offline case, and it is worth distinguishing from a 5xx because
    // the UI reacts differently: "JARVIS isn't running" rather than
    // "JARVIS is unhappy".
    //
    // The original rejection is kept as `cause`: "Failed to fetch" and a
    // CORS rejection are the same class of failure to the UI but very
    // different to whoever is debugging it, and this is the only place
    // that distinction still exists.
    throw new ApiError(
      {
        code: "BACKEND_UNREACHABLE",
        message: "The JARVIS backend is not reachable.",
        recovery_action: "Check that the JARVIS process is running.",
        severity: "error",
        retryable: true,
      },
      0,
      { cause },
    );
  }
}

/** One resource. Throws `ApiError` on any non-2xx. */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await send(path, options);
  if (response.status === 204) return undefined as T;

  const body = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) throw toApiError(response.status, body);
  assertEnvelope(body, path, response.status);
  return (body as ApiEnvelope<T>).data;
}

/**
 * A 2xx whose body is not the `{data, meta}` envelope.
 *
 * Reading `.data` (or `.meta`) off it would throw a bare `TypeError` from
 * inside the client, naming nothing and bypassing every error path the
 * app has. An `ApiError` at least names the route that misbehaved and
 * flows through `describeError` like any other failure.
 */
function assertEnvelope(body: unknown, path: string, status: number): void {
  if (body !== null && typeof body === "object") return;
  throw new ApiError(
    {
      code: "MALFORMED_RESPONSE",
      message: `${path} returned a success status with no response envelope.`,
      recovery_action: null,
      severity: "error",
      retryable: false,
    },
    status,
  );
}

/** A collection, keeping the pagination `meta` the caller needs to page.
 *  Separate from `apiRequest` rather than a flag, so the return type
 *  differs and a caller cannot silently ignore `has_more`. */
export async function apiList<T>(path: string, options: RequestOptions = {}): Promise<Page<T>> {
  const response = await send(path, options);
  const body = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) throw toApiError(response.status, body);

  assertEnvelope(body, path, response.status);
  const envelope = body as ApiEnvelope<T[]>;
  const meta = (envelope.meta ?? {}) as Partial<PageMeta>;
  const items = envelope.data ?? [];
  return {
    items,
    meta: {
      count: meta.count ?? items.length,
      limit: meta.limit ?? items.length,
      offset: meta.offset ?? 0,
      has_more: meta.has_more ?? false,
      ...meta,
    },
  };
}

/** A request whose response body is not needed (204s, mostly). */
export async function apiVoid(path: string, options: RequestOptions = {}): Promise<void> {
  const response = await send(path, options);
  if (response.ok) return;
  const body = (await response.json().catch(() => null)) as unknown;
  throw toApiError(response.status, body);
}
