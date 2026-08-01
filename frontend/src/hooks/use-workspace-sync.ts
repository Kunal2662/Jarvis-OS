import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { workspaceManager } from "@/core/workspace-manager";

/**
 * The one place React Router's URL state actually drives module
 * lifecycle -- calls `workspaceManager.switchTo()` on every pathname
 * change, and unmounts whatever's active if this hook itself unmounts
 * (app teardown), so no module is ever left mounted with nothing
 * driving it. Mounted once, from `components/layout/workspace.tsx`.
 */
export function useWorkspaceSync(): void {
  const location = useLocation();

  useEffect(() => {
    workspaceManager.switchTo(location.pathname);
  }, [location.pathname]);

  useEffect(() => {
    return () => workspaceManager.unmountActive();
  }, []);
}
