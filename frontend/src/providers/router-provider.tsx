import { RouterProvider as ReactRouterProvider } from "react-router-dom";
import { router } from "@/routes/router";

/** Thin wrapper so the composition root (App.tsx) lists this alongside
 *  every other provider uniformly, per the requested provider set. */
export function RouterProvider() {
  return <ReactRouterProvider router={router} />;
}
