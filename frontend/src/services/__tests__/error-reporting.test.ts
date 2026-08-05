import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api/client";
import {
  describeError,
  isSuppressedByConnectionState,
  reportError,
  reportSuccess,
} from "@/services/error-reporting";

const toastCalls: Array<{ kind: string; title: string; description?: string }> = [];

vi.mock("sonner", () => {
  const record =
    (kind: string) =>
    (title: string, options?: { description?: string }) => {
      toastCalls.push({ kind, title, description: options?.description });
    };
  return { toast: { error: record("error"), warning: record("warning"), success: record("success") } };
});

function apiError(status: number, message: string, code = `HTTP_${status}`): ApiError {
  return new ApiError(
    {
      code,
      message,
      recovery_action: null,
      severity: status >= 500 ? "error" : "warning",
      retryable: status >= 500,
    },
    status,
  );
}

beforeEach(() => {
  toastCalls.length = 0;
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("describeError", () => {
  it("names the offline case for what it is", () => {
    const described = describeError(
      new ApiError(
        {
          code: "BACKEND_UNREACHABLE",
          message: "The JARVIS backend is not reachable.",
          recovery_action: "Check that the JARVIS process is running.",
          severity: "error",
          retryable: true,
        },
        0,
      ),
    );

    expect(described.title).toBe("JARVIS isn't running");
    expect(described.action).toBe("Check that the JARVIS process is running.");
  });

  it("treats 401 as a recoverable session problem, not an error", () => {
    const described = describeError(apiError(401, "Invalid session"));
    expect(described.title).toBe("Session expired");
    expect(described.severity).toBe("warning");
  });

  it("distinguishes 403 from 404", () => {
    expect(describeError(apiError(403, "no")).title).toBe("Not permitted");
    expect(describeError(apiError(404, "gone")).title).toBe("Not found");
  });

  it("uses the backend's own wording for a 400", () => {
    const described = describeError(apiError(400, "Title must not be empty."));
    expect(described.title).toBe("Title must not be empty.");
    expect(described.detail).toBe("");
  });

  it("offers a retry for a retryable 5xx", () => {
    const described = describeError(apiError(503, "overloaded"));
    expect(described.title).toBe("JARVIS hit an error");
    expect(described.action).toBe("Try again.");
    expect(described.severity).toBe("error");
  });

  it("handles a plain Error and a thrown non-Error", () => {
    expect(describeError(new Error("boom")).detail).toBe("boom");
    expect(describeError("just a string").detail).toBe("just a string");
  });
});

describe("reportError", () => {
  it("shows a warning toast for a 4xx with the action appended", () => {
    const error = new ApiError(
      {
        code: "HTTP_403",
        message: "Denied",
        recovery_action: "Ask an operator.",
        severity: "warning",
        retryable: false,
      },
      403,
    );

    expect(reportError(error, { context: "Couldn't open the file" })).toBe(true);
    expect(toastCalls).toEqual([
      {
        kind: "warning",
        title: "Couldn't open the file: Not permitted",
        description: "Denied Ask an operator.",
      },
    ]);
  });

  it("shows an error toast for a 5xx", () => {
    reportError(apiError(500, "kaboom"));
    expect(toastCalls[0].kind).toBe("error");
  });

  it("stays silent when the offline state already says it", () => {
    const offline = new ApiError(
      {
        code: "BACKEND_UNREACHABLE",
        message: "unreachable",
        recovery_action: null,
        severity: "error",
        retryable: true,
      },
      0,
    );

    expect(reportError(offline)).toBe(false);
    expect(toastCalls).toEqual([]);
    expect(isSuppressedByConnectionState(offline)).toBe(true);
  });

  it("still speaks up for an offline failure when forced", () => {
    const offline = new ApiError(
      {
        code: "BACKEND_UNREACHABLE",
        message: "unreachable",
        recovery_action: null,
        severity: "error",
        retryable: true,
      },
      0,
    );

    expect(reportError(offline, { force: true })).toBe(true);
    expect(toastCalls).toHaveLength(1);
  });

  it("logs the real object regardless of whether it toasts", () => {
    const spy = console.error as unknown as ReturnType<typeof vi.fn>;
    reportError(apiError(500, "kaboom"));
    expect(spy).toHaveBeenCalled();
  });

  it("omits the description when there is nothing to add", () => {
    reportError(apiError(400, "Title must not be empty."));
    expect(toastCalls[0].description).toBeUndefined();
  });
});

describe("reportSuccess", () => {
  it("uses the same surface as the failure path", () => {
    reportSuccess("Saved");
    expect(toastCalls).toEqual([{ kind: "success", title: "Saved", description: undefined }]);
  });
});
