/**
 * The Storage Framework -- per Task 7's explicit rule, "no module
 * directly manages storage": every module gets a namespaced
 * `ModuleStorage` instance from this file instead of touching
 * `localStorage` (or Tauri's filesystem/store APIs, once wired) itself.
 * Maps onto ARCHITECTURE.md section 12's storage-tier table:
 *
 * | Tier        | Backing today                          | Matches ARCHITECTURE.md section 12 row |
 * |-------------|------------------------------------------|------------------------------------------|
 * | memory      | in-process `Map`, cleared on reload       | "Cache" (in-process variant)              |
 * | persistent  | `localStorage`, namespaced per module     | "Persistent, non-secret"                  |
 * | cache       | `localStorage`, explicitly clear-safe     | "Cache" (cross-restart variant)           |
 * | encrypted   | throws -- routes to Secrets Management once it exists, never browser-side crypto | "Encrypted / Secrets" |
 *
 * "Cloud Sync Ready" (Task 7) is a marker, not a sync implementation --
 * `markSyncable()` tags a persistent key as eligible for M11's Oracle
 * Cloud sync; the actual sync mechanism is M11 backend scope, never
 * built here.
 */

export class EncryptedStorageNotAvailableError extends Error {
  constructor(moduleId: string) {
    super(
      `${moduleId}: encrypted storage is not available in the browser/frontend layer. ` +
        "Secrets must be written through the backend's Secrets Management system " +
        "(ARCHITECTURE.md section 17, M14) once its API exists -- never implemented " +
        "as client-side crypto, which cannot actually keep a secret from the user's own machine.",
    );
  }
}

interface CacheEntry<T> {
  value: T;
  expiresAt: number | null;
}

export class ModuleStorage {
  private readonly moduleId: string;
  private readonly memoryStore = new Map<string, unknown>();
  private readonly syncableKeys = new Set<string>();

  constructor(moduleId: string) {
    this.moduleId = moduleId;
  }

  private key(namespace: string, id: string): string {
    return `jarvis.${namespace}.${this.moduleId}.${id}`;
  }

  // --- Memory (cleared on reload, never persisted) ----------------------
  memory = {
    get: <T>(id: string): T | undefined => this.memoryStore.get(id) as T | undefined,
    set: <T>(id: string, value: T): void => void this.memoryStore.set(id, value),
    delete: (id: string): void => void this.memoryStore.delete(id),
    clear: (): void => this.memoryStore.clear(),
  };

  // --- Persistent (survives restart, source-of-truth data) --------------
  persistent = {
    get: <T>(id: string): T | undefined => {
      const raw = localStorage.getItem(this.key("data", id));
      return raw ? (JSON.parse(raw) as T) : undefined;
    },
    set: <T>(id: string, value: T): void => {
      localStorage.setItem(this.key("data", id), JSON.stringify(value));
    },
    delete: (id: string): void => localStorage.removeItem(this.key("data", id)),
    /** Tag this key as eligible for M11's Oracle Cloud sync once that
     *  backend exists -- a marker only, per this file's own header. */
    markSyncable: (id: string): void => void this.syncableKeys.add(this.key("data", id)),
    isSyncable: (id: string): boolean => this.syncableKeys.has(this.key("data", id)),
  };

  // --- Cache (persistent, but explicitly, always safe to wipe) ----------
  cache = {
    get: <T>(id: string): T | undefined => {
      const raw = localStorage.getItem(this.key("cache", id));
      if (!raw) return undefined;
      const entry = JSON.parse(raw) as CacheEntry<T>;
      if (entry.expiresAt && Date.now() > entry.expiresAt) {
        localStorage.removeItem(this.key("cache", id));
        return undefined;
      }
      return entry.value;
    },
    set: <T>(id: string, value: T, ttlMs?: number): void => {
      const entry: CacheEntry<T> = { value, expiresAt: ttlMs ? Date.now() + ttlMs : null };
      localStorage.setItem(this.key("cache", id), JSON.stringify(entry));
    },
    /** Every cache entry for this module -- safe to call unconditionally,
     *  per ARCHITECTURE.md section 12: "a service that can't function
     *  after its cache is wiped has a bug, not a caching strategy." */
    clear: (): void => {
      const prefix = this.key("cache", "");
      for (const storageKey of Object.keys(localStorage)) {
        if (storageKey.startsWith(prefix)) localStorage.removeItem(storageKey);
      }
    },
  };

  // --- Encrypted (not available client-side, by design) -----------------
  encrypted = {
    get: (_id: string): never => {
      throw new EncryptedStorageNotAvailableError(this.moduleId);
    },
    set: (_id: string, _value: unknown): never => {
      throw new EncryptedStorageNotAvailableError(this.moduleId);
    },
  };
}

const instances = new Map<string, ModuleStorage>();

/** One `ModuleStorage` per module id, reused across calls -- modules
 *  never construct their own instance directly. */
export function getModuleStorage(moduleId: string): ModuleStorage {
  let storage = instances.get(moduleId);
  if (!storage) {
    storage = new ModuleStorage(moduleId);
    instances.set(moduleId, storage);
  }
  return storage;
}
