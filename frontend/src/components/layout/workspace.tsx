import { AnimatePresence, motion } from "motion/react";
import { useLocation, Outlet } from "react-router-dom";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useWorkspaceSync } from "@/hooks/use-workspace-sync";
import { pageTransition, pageTransitionVariants } from "@/lib/motion";

/**
 * Layout component only -- the scrollable content region every route
 * renders into via React Router's `<Outlet />`. `useWorkspaceSync()`
 * (Phase 3, Task Group B) is the one place routing actually drives
 * module lifecycle: on every pathname change it resolves and mounts the
 * real `BaseApplication` instance owning that route through
 * `ApplicationRegistry`, unmounting whichever module was previously
 * active -- a separate concern from the fade/rise transition below,
 * which is purely visual and owns no module lifecycle of its own. A
 * module's own page component still decides what actually renders in
 * the `<Outlet />` -- this component doesn't render per-module content.
 */
export function Workspace() {
  const location = useLocation();
  useWorkspaceSync();

  return (
    <ScrollArea className="h-full">
      <main className="p-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial="initial"
            animate="animate"
            exit="exit"
            variants={pageTransitionVariants}
            transition={pageTransition}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </ScrollArea>
  );
}
