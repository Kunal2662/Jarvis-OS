import { Suspense, type ReactElement } from "react";
import type { RouteObject } from "react-router-dom";
import { createBrowserRouter } from "react-router-dom";
import { LoadingState } from "@/components/common/loading-spinner";
import { DesktopShell } from "@/components/layout/desktop-shell";
import { DashboardGrid } from "@/features/dashboard/dashboard-grid";
import { MODULE_DEFINITIONS } from "@/modules/module-definitions";
import { SettingsRoute, VoiceRoute, WorkspaceRoute } from "@/routes/lazy-routes";
import { PlaceholderRoute } from "@/routes/placeholder-route";

/**
 * One route per registered module (`modules/module-definitions.ts`),
 * plus the workspace route M8 Phase 3 adds. See MASTER_ROADMAP.md §8 for
 * which implementation phase builds each module's real route element.
 * `createBrowserRouter` (not `HashRouter`) since Tauri serves the app
 * from its own asset protocol, which supports real paths.
 *
 * Built as two explicit branches (index vs. non-index), not a single
 * object with a conditional `path: undefined` -- mixing `index: true`
 * with an explicit `path` key (even `undefined`) produced a real bug in
 * testing: the sidebar highlighted the wrong item while the correct
 * content still rendered. `RouteObject`'s index/non-index shapes are a
 * discriminated union for a reason.
 *
 * **Code splitting (M8 Phase 3).** Phase 1's note here said to switch a
 * route to `React.lazy()` "once a route gets its own real, substantial
 * feature module". Three now have: Workspace, Voice and Settings, each
 * landing in its own chunk (see `routes/lazy-routes.ts`, which holds the
 * components so this file can keep exporting `router` without breaking
 * their Fast Refresh). Two deliberately stay eager:
 *
 * - `PlaceholderRoute` -- ~1KB shared by eleven routes; splitting it
 *   would add a round-trip per route for no benefit.
 * - `DashboardGrid` -- the app's own landing route. Lazily loading the
 *   first thing every user sees trades a smaller initial bundle for a
 *   visible delay on the one screen that must feel instant.
 *   `core/panel-registry.ts` imports it statically for the same reason;
 *   importing it dynamically there while importing it statically here
 *   would produce a build warning and no second chunk, since a module
 *   statically imported anywhere cannot be split out.
 */

/** Every lazy route shares one fallback, so a route loading looks the
 *  same wherever it happens -- and the same as a panel loading, which
 *  `components/workspace/panel-frame.tsx` renders identically. */
function lazyRoute(element: ReactElement): ReactElement {
  return <Suspense fallback={<LoadingState />}>{element}</Suspense>;
}

const REAL_ROUTE_ELEMENTS: Partial<Record<string, ReactElement>> = {
  home: <DashboardGrid />,
  voice: lazyRoute(<VoiceRoute />),
  settings: lazyRoute(<SettingsRoute />),
};

const childRoutes: RouteObject[] = MODULE_DEFINITIONS.map((manifest) => {
  const route = manifest.routes[0] ?? "/";
  const element = REAL_ROUTE_ELEMENTS[manifest.name] ?? <PlaceholderRoute label={manifest.displayName} />;
  return route === "/" ? { index: true, element } : { path: route.slice(1), element };
});

/**
 * `/workspace` is not a module route.
 *
 * It has no `MODULE_DEFINITIONS` entry deliberately: the workspace is
 * the shell's own surface for arranging *other* modules' panels, not a
 * module that could be disabled, and giving it a manifest would put it
 * in the Sidebar's module list as a peer of the things it contains.
 * Reached from the Header instead.
 */
childRoutes.push({ path: "workspace", element: lazyRoute(<WorkspaceRoute />) });

export const router = createBrowserRouter([
  {
    path: "/",
    element: <DesktopShell />,
    children: childRoutes,
  },
]);
