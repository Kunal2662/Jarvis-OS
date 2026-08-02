import type { RouteObject } from "react-router-dom";
import { createBrowserRouter } from "react-router-dom";
import { DesktopShell } from "@/components/layout/desktop-shell";
import { MODULE_DEFINITIONS } from "@/modules/module-definitions";
import { PlaceholderRoute } from "@/routes/placeholder-route";

/**
 * One route per registered module (`modules/module-definitions.ts`),
 * all rendering the shared placeholder for now -- see
 * MASTER_ROADMAP.md section 8 for which implementation phase actually
 * builds each module's real route element. `routes/nav-items.ts` is no
 * longer this file's source; it's read by nothing in the app anymore.
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
 * Performance foundation note (Task 17): every route below intentionally
 * imports `PlaceholderRoute` eagerly, not via `React.lazy()` -- splitting
 * a single ~1KB component shared by all 14 routes would add a network
 * round-trip for zero benefit. Once a route gets its own real,
 * substantial feature module, replace its `element` with:
 *
 *   const GmailModule = lazy(() => import("@/features/gmail"));
 *   element: <Suspense fallback={<LoadingState />}><GmailModule /></Suspense>
 *
 * -- one lazy import per real feature module, following
 * `components/common/loading-spinner.tsx`'s `LoadingState` as the
 * fallback, consistent with every other module's own code-split chunk.
 */
const childRoutes: RouteObject[] = MODULE_DEFINITIONS.map((manifest) => {
  const route = manifest.routes[0] ?? "/";
  return route === "/"
    ? { index: true, element: <PlaceholderRoute label={manifest.displayName} /> }
    : { path: route.slice(1), element: <PlaceholderRoute label={manifest.displayName} /> };
});

export const router = createBrowserRouter([
  {
    path: "/",
    element: <DesktopShell />,
    children: childRoutes,
  },
]);
