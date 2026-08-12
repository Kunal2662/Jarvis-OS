import { lazy } from "react";

/**
 * The code-split route components -- M8 Phase 3's "Route Splitting".
 *
 * A module of their own rather than inline in `routes/router.tsx`
 * because that file exports `router`, a value, and defining components
 * alongside it breaks Fast Refresh for every one of them (oxlint's
 * `react(only-export-components)` says exactly this). A separate module
 * that exports only components refreshes correctly and keeps the router
 * file about routing.
 *
 * Each `lazy()` below becomes its own build chunk, fetched the first
 * time its route is visited. `panel-frame.tsx` and `router.tsx` both
 * render these inside a `<Suspense>` with the same `LoadingState`, so a
 * route loading and a panel loading are indistinguishable to the user.
 */

export const WorkspaceRoute = lazy(async () => ({
  default: (await import("@/components/workspace/workspace-container")).WorkspaceContainer,
}));

export const VoiceRoute = lazy(async () => ({
  default: (await import("@/features/voice/voice-page")).VoicePage,
}));

export const SettingsRoute = lazy(async () => ({
  default: (await import("@/features/settings/settings-page")).SettingsPage,
}));

export const InstallerRoute = lazy(async () => ({
  default: (await import("@/features/installer/installer-route")).InstallerRoute,
}));
