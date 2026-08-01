import { beforeEach, describe, expect, it, vi } from "vitest";
import { PermissionFramework } from "@/core/permission-framework";

describe("PermissionFramework", () => {
  let permissions: PermissionFramework;

  beforeEach(() => {
    permissions = new PermissionFramework();
  });

  it("a scope with no grant reads as not granted", () => {
    expect(permissions.isGranted("mod-a", "network")).toBe(false);
  });

  it("always_allow grants read as granted", () => {
    permissions.grant("mod-a", "network", "always_allow");
    expect(permissions.isGranted("mod-a", "network")).toBe(true);
  });

  it("always_deny reads as not granted even though a grant record exists", () => {
    permissions.grant("mod-a", "network", "always_deny");
    expect(permissions.isGranted("mod-a", "network")).toBe(false);
  });

  it("a temporary grant expires", () => {
    vi.useFakeTimers();
    const now = new Date("2026-01-01T00:00:00Z");
    vi.setSystemTime(now);

    permissions.grant("mod-a", "notifications", "temporary", new Date(now.getTime() + 1000).toISOString());
    expect(permissions.isGranted("mod-a", "notifications")).toBe(true);

    vi.advanceTimersByTime(2000);
    expect(permissions.isGranted("mod-a", "notifications")).toBe(false);

    vi.useRealTimers();
  });

  it("revoke removes a grant", () => {
    permissions.grant("mod-a", "filesystem", "always_allow");
    permissions.revoke("mod-a", "filesystem");
    expect(permissions.isGranted("mod-a", "filesystem")).toBe(false);
  });

  it("permissions are scoped per module -- one module's grant never leaks to another", () => {
    permissions.grant("mod-a", "network", "always_allow");
    expect(permissions.isGranted("mod-b", "network")).toBe(false);
  });

  it("getGrantsFor returns only that module's grants", () => {
    permissions.grant("mod-a", "network", "always_allow");
    permissions.grant("mod-a", "filesystem", "always_allow");
    permissions.grant("mod-b", "network", "always_allow");

    expect(permissions.getGrantsFor("mod-a")).toHaveLength(2);
  });

  it("records every check/grant/revoke/denial in history", () => {
    permissions.grant("mod-a", "network", "always_allow");
    permissions.isGranted("mod-a", "network"); // checked
    permissions.isGranted("mod-a", "hotkey"); // denied (no grant)
    permissions.revoke("mod-a", "network");

    const events = permissions.getHistory("mod-a").map((e) => e.event);
    expect(events).toEqual(["granted", "checked", "denied", "revoked"]);
  });
});
