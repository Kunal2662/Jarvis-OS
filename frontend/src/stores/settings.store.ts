import { create } from "zustand";
import { settingsApi, type SettingsTree } from "@/services/api/endpoints";
import { describeError } from "@/services/error-reporting";

/**
 * The backend's configuration tree -- M8 Phase 2's "Settings: API layer +
 * store, real backend-backed values only".
 *
 * **Not a duplicate of `core/settings-framework.ts`.** That framework
 * owns *per-module client* settings: a module's own schema, versioned and
 * migrated, persisted locally because it describes how this desktop
 * client behaves. This store owns the *Python process's* configuration --
 * the pydantic-settings tree assembled from `.env` and defaults. Two
 * different things with two different owners and two different
 * lifetimes; collapsing them would mean either shipping module UI
 * preferences to the backend or caching backend configuration in
 * `localStorage`, and both are wrong.
 *
 * **Read-only, deliberately.** `GET /api/v1/settings` is the whole
 * surface the backend exposes; writing a setting means writing `.env`,
 * which belongs to the Configuration Manager work in a later milestone.
 * A store that offered `set()` against an endpoint that does not exist
 * would be exactly the "simulated completed functionality" this phase
 * forbids.
 *
 * **Secrets never arrive here.** The backend redacts them
 * (`SettingsService.public_snapshot()`); this store does no redaction of
 * its own, because a second redaction layer implies the first might be
 * incomplete, and the fix for that is on the server.
 */
interface SettingsStoreShape {
  /** `null` until the first successful load -- distinguishable from "the
   *  backend returned an empty tree", which never happens but would
   *  otherwise be indistinguishable from "not loaded yet". */
  tree: SettingsTree | null;
  loading: boolean;
  /** Human-readable load failure, or `null`. Kept in the store rather
   *  than toasted: a settings page that failed to load should say so in
   *  place, not fire a transient notification and render blank. */
  error: string | null;

  load: () => Promise<void>;
  /** A single value by dotted key (`"ui.theme"`), read from the loaded
   *  tree. Returns `undefined` for an unknown key or an unloaded tree --
   *  the caller decides whether that is an error, because for an
   *  optional setting it is not. */
  get: (dottedKey: string) => unknown;
}

function readPath(tree: SettingsTree | null, dottedKey: string): unknown {
  if (!tree) return undefined;
  let cursor: unknown = tree;
  for (const segment of dottedKey.split(".")) {
    if (cursor === null || typeof cursor !== "object") return undefined;
    cursor = (cursor as Record<string, unknown>)[segment];
  }
  return cursor;
}

export const useSettingsStore = create<SettingsStoreShape>()((set, get) => ({
  tree: null,
  loading: false,
  error: null,

  load: async () => {
    set({ loading: true, error: null });
    try {
      set({ tree: await settingsApi.all(), loading: false });
    } catch (error) {
      // Described, not raw: the settings page shows this string, and
      // `describeError` is the single place that decides what a failure
      // reads like to a human.
      const { title, detail } = describeError(error);
      set({ loading: false, error: detail ? `${title} ${detail}` : title });
    }
  },

  get: (dottedKey) => readPath(get().tree, dottedKey),
}));
