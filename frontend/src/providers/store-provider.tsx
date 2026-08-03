import { useEffect, useState } from "react";
import { useDockStore } from "@/stores/dock.store";
import { useSidebarStore } from "@/stores/sidebar.store";
import { useStartupPreferencesStore } from "@/stores/startup-preferences.store";
import { useThemeStore } from "@/stores/theme.store";
import { useWindowStore } from "@/stores/window.store";

const persistedStores = [useThemeStore, useSidebarStore, useDockStore, useWindowStore, useStartupPreferencesStore];

/**
 * Blocks the first render until every persisted Zustand store has
 * finished rehydrating from storage -- otherwise the UI briefly flashes
 * default values (e.g. the light theme) before snapping to the user's
 * saved preference. Not a React Context: Zustand stores are already
 * globally accessible via their own hooks, so this provider's only job
 * is the hydration gate, not dependency injection.
 */
export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [isHydrated, setIsHydrated] = useState(() =>
    persistedStores.every((store) => store.persist.hasHydrated()),
  );

  useEffect(() => {
    if (isHydrated) return;
    const unsubscribes = persistedStores.map((store) =>
      store.persist.onFinishHydration(() => {
        if (persistedStores.every((s) => s.persist.hasHydrated())) {
          setIsHydrated(true);
        }
      }),
    );
    return () => {
      for (const unsubscribe of unsubscribes) unsubscribe();
    };
  }, [isHydrated]);

  if (!isHydrated) return null;
  return children;
}
