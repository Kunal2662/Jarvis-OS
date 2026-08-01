import { beforeEach, describe, expect, it, vi } from "vitest";
import { EncryptedStorageNotAvailableError, ModuleStorage } from "@/core/storage-framework";

describe("ModuleStorage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("memory tier does not persist across instances", () => {
    const storage = new ModuleStorage("mod-a");
    storage.memory.set("key", "value");
    expect(storage.memory.get("key")).toBe("value");

    const fresh = new ModuleStorage("mod-a");
    expect(fresh.memory.get("key")).toBeUndefined();
  });

  it("persistent tier survives a fresh instance (backed by localStorage)", () => {
    const storage = new ModuleStorage("mod-a");
    storage.persistent.set("key", { foo: "bar" });

    const fresh = new ModuleStorage("mod-a");
    expect(fresh.persistent.get("key")).toEqual({ foo: "bar" });
  });

  it("storage is namespaced per module -- one module never reads another's data", () => {
    const a = new ModuleStorage("mod-a");
    const b = new ModuleStorage("mod-b");
    a.persistent.set("key", "a-value");
    expect(b.persistent.get("key")).toBeUndefined();
  });

  it("cache entries expire after their TTL", () => {
    vi.useFakeTimers();
    const storage = new ModuleStorage("mod-a");
    storage.cache.set("key", "value", 1000);
    expect(storage.cache.get("key")).toBe("value");

    vi.advanceTimersByTime(1500);
    expect(storage.cache.get("key")).toBeUndefined();
    vi.useRealTimers();
  });

  it("cache.clear() wipes only this module's cache, never persistent data or other modules' caches", () => {
    const a = new ModuleStorage("mod-a");
    const b = new ModuleStorage("mod-b");
    a.cache.set("key", "cached");
    a.persistent.set("key", "persisted");
    b.cache.set("key", "other-module-cached");

    a.cache.clear();

    expect(a.cache.get("key")).toBeUndefined();
    expect(a.persistent.get("key")).toBe("persisted");
    expect(b.cache.get("key")).toBe("other-module-cached");
  });

  it("encrypted storage throws rather than pretending to be secure", () => {
    const storage = new ModuleStorage("mod-a");
    expect(() => storage.encrypted.set("secret", "value")).toThrow(EncryptedStorageNotAvailableError);
    expect(() => storage.encrypted.get("secret")).toThrow(EncryptedStorageNotAvailableError);
  });

  it("markSyncable/isSyncable tag a key without touching its value", () => {
    const storage = new ModuleStorage("mod-a");
    storage.persistent.set("key", "value");
    expect(storage.persistent.isSyncable("key")).toBe(false);

    storage.persistent.markSyncable("key");
    expect(storage.persistent.isSyncable("key")).toBe(true);
    expect(storage.persistent.get("key")).toBe("value");
  });
});
