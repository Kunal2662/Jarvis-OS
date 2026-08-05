/**
 * The one way a failure becomes visible -- M8 Phase 2's "single,
 * consistent error-boundary + toast pattern for the whole app".
 *
 * Two surfaces, one decision function. `ErrorBoundary`
 * (`providers/error-boundary.tsx`, Phase 1) already owns the *render*
 * failure case: something threw during render, the subtree is gone, and a
 * full-screen fallback is the only honest thing to show. This module owns
 * the other case -- an action failed but the UI is intact -- where
 * replacing the screen would be a wild overreaction and a toast is right.
 *
 * The reason to centralise it is `ApiError`. A 401 is not a 500 is not
 * "the backend isn't running", and every call site deciding that for
 * itself is how an app ends up telling a user "Request failed with status
 * 0" when the truth is that JARVIS is not started. `describeError` makes
 * that judgement once.
 *
 * **Offline is not an error toast.** When the backend is unreachable the
 * app has a real state for that (`stores/connection.store.ts`) and shows
 * it persistently; firing a toast per failed request on top would produce
 * a stack of identical complaints about a condition already on screen. So
 * `reportError` deliberately returns without toasting in that case, and
 * says so via its return value rather than silently.
 */

import { toast } from "sonner";
import { ApiError } from "@/services/api/client";

export interface ErrorDescription {
  title: string;
  /** Empty when the title says everything worth saying. */
  detail: string;
  severity: "warning" | "error";
  /** What the user could do about it, when there is something. */
  action: string | null;
}

/**
 * Turn anything throwable into the text a human should read. Pure --
 * no toasting, no logging -- so tests and non-toast surfaces (an inline
 * form error, Developer Mode's console) can reuse the same judgement.
 */
export function describeError(error: unknown): ErrorDescription {
  if (error instanceof ApiError) {
    if (error.isOffline) {
      return {
        title: "JARVIS isn't running",
        detail: "The backend is not reachable.",
        severity: "error",
        action: error.recoveryAction,
      };
    }
    if (error.status === 401) {
      return {
        title: "Session expired",
        detail: error.message,
        severity: "warning",
        action: "Reconnect to continue.",
      };
    }
    if (error.status === 403) {
      return {
        title: "Not permitted",
        detail: error.message,
        severity: "warning",
        action: error.recoveryAction,
      };
    }
    if (error.status === 404) {
      return { title: "Not found", detail: error.message, severity: "warning", action: null };
    }
    if (error.status >= 500) {
      return {
        title: "JARVIS hit an error",
        detail: error.message,
        severity: "error",
        action: error.retryable ? "Try again." : null,
      };
    }
    // 400 and the rest of 4xx: the backend's `detail` string is written
    // for a human by the service layer, so it is the whole message.
    return { title: error.message, detail: "", severity: "warning", action: error.recoveryAction };
  }

  if (error instanceof Error) {
    return { title: "Something went wrong", detail: error.message, severity: "error", action: null };
  }
  return { title: "Something went wrong", detail: String(error), severity: "error", action: null };
}

/** Whether this failure is already represented by a persistent UI state,
 *  making a toast redundant noise. */
export function isSuppressedByConnectionState(error: unknown): boolean {
  return error instanceof ApiError && error.isOffline;
}

export interface ReportOptions {
  /** Prefix describing what the user was doing -- "Couldn't save the
   *  note". Without it the toast says what broke but not what failed. */
  context?: string;
  /** Show the toast even when the app is already displaying an offline
   *  state. Only for actions the user explicitly triggered, where silence
   *  would read as the click doing nothing. */
  force?: boolean;
}

/**
 * Report a failure to the user. Returns whether a toast was actually
 * shown, so a caller that needs a guaranteed acknowledgement can tell.
 */
export function reportError(error: unknown, options: ReportOptions = {}): boolean {
  const described = describeError(error);

  // Always log the real object: the toast is deliberately lossy, and
  // Developer Mode / the console is where the full thing belongs.
  // eslint-disable-next-line no-console -- same sanctioned sink as
  // `providers/error-boundary.tsx`, until the loguru relay exists.
  console.error("[reportError]", options.context ?? "", error);

  if (!options.force && isSuppressedByConnectionState(error)) return false;

  const title = options.context ? `${options.context}: ${described.title}` : described.title;
  const description = [described.detail, described.action].filter(Boolean).join(" ");

  if (described.severity === "warning") {
    toast.warning(title, description ? { description } : undefined);
  } else {
    toast.error(title, description ? { description } : undefined);
  }
  return true;
}

/** The success half of the same pattern, so call sites do not reach for
 *  `sonner` directly for the happy path and this module for the sad one. */
export function reportSuccess(message: string, description?: string): void {
  toast.success(message, description ? { description } : undefined);
}
