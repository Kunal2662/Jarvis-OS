import { useEffect } from "react";
import { motion, type Variants } from "motion/react";
import { CommandPaletteLayer } from "@/components/layout/command-palette-layer";
import { ContextMenuLayer } from "@/components/layout/context-menu-layer";
import { Dock } from "@/components/layout/dock";
import { Header } from "@/components/layout/header";
import { NotificationLayer } from "@/components/layout/notification-layer";
import { Sidebar } from "@/components/layout/sidebar";
import { StatusBar } from "@/components/layout/status-bar";
import { WindowLayer } from "@/components/layout/window-layer";
import { Workspace } from "@/components/layout/workspace";
import { DeveloperPanel } from "@/features/developer/developer-panel";
import { useGlassEffectsEnabled } from "@/hooks/use-glass-effects";
import { windowService } from "@/services/window/window-service";

/** Plays once on `DesktopShell`'s own first mount -- which, since
 *  `components/startup/startup-gate.tsx` (Phase 4, Task Group I) only
 *  reveals the real route tree once startup is done, naturally IS the
 *  "just finished waking up" moment the Dashboard Reveal sequence
 *  describes (Sidebar → Search/Header → Workspace content, staggered)
 *  -- no separate "startup just completed" signal needs to be threaded
 *  in from outside; DesktopShell mounting is that signal. Respects
 *  `MotionConfig`'s app-wide `reducedMotion="user"` automatically like
 *  every other declarative Motion `animate` in this app. */
const shellVariants: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08, delayChildren: 0.05 } },
};
const regionVariants: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: "easeOut" } },
};

/**
 * The root layout every route renders inside (see routes/router.tsx).
 * Owns 8 dedicated regions per MASTER_ROADMAP.md M8 Phase 3: Sidebar,
 * Dock, Workspace, Status Bar, Window Layer, Notification Layer, Context
 * Menu Layer, Command Palette Layer -- so a future task group fills in
 * an already-named slot instead of restructuring this component again.
 * Developer Panel is a ninth, pre-existing region from Phase 1/2, kept
 * as-is; it isn't one of the 8 named regions but has always lived here.
 * Pure composition -- the one piece of real logic (subscribing to native
 * window state) is unchanged from Phase 1. Sidebar/Dock's own internals
 * are untouched in this task group -- they still render from
 * `routes/nav-items.ts`, not the registry (that's a later task group).
 *
 * The two fixed glow blobs (added Task Group J, Glass design system)
 * are the only reason any glass surface elsewhere -- Sidebar, Command
 * Palette, Card -- has real visual content behind it to blur; a flat
 * `bg-background` alone gives `backdrop-blur` nothing to do. `aria-hidden`
 * since they're purely decorative, and skipped entirely (not just
 * hidden) when glass effects are disabled -- backdrop-filter is one of
 * the more expensive things a browser can paint, so an unused blur
 * target shouldn't stay mounted.
 */
export function DesktopShell() {
  useEffect(() => {
    let unsubscribe: (() => void) | undefined;
    windowService.subscribeToWindowState().then((unsub) => {
      unsubscribe = unsub;
    });
    return () => unsubscribe?.();
  }, []);

  const glassEffectsEnabled = useGlassEffectsEnabled();

  return (
    <motion.div
      className="relative flex h-svh flex-col overflow-hidden bg-background text-foreground"
      initial="hidden"
      animate="visible"
      variants={shellVariants}
    >
      {glassEffectsEnabled && (
        <div
          data-testid="ambient-glow"
          aria-hidden="true"
          className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"
        >
          <div className="-top-40 -left-40 absolute size-96 rounded-full bg-accent/10 blur-3xl" />
          <div className="-right-40 -bottom-40 absolute size-96 rounded-full bg-primary/10 blur-3xl" />
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <motion.div variants={regionVariants}>
          <Sidebar />
        </motion.div>
        <motion.div className="flex min-w-0 flex-1 flex-col" variants={regionVariants}>
          <Header />
          <Workspace />
        </motion.div>
      </div>
      <motion.div variants={regionVariants}>
        <StatusBar />
      </motion.div>
      <motion.div variants={regionVariants}>
        <Dock />
      </motion.div>
      <DeveloperPanel />
      <WindowLayer />
      <NotificationLayer />
      <ContextMenuLayer />
      <CommandPaletteLayer />
    </motion.div>
  );
}
