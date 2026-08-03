import type { ComponentType } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Lock, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { DEVELOPER_PANEL_SECTIONS } from "@/features/developer/panel-sections";
import { ModuleStateInspector } from "@/features/developer/module-state-inspector";
import { StartupPreview } from "@/features/developer/startup-preview";
import { VoiceStatePreview } from "@/features/developer/voice-state-preview";
import { useDeveloperModeStore } from "@/stores/developer-mode.store";
import { MOTION_DURATIONS } from "@/lib/motion";

/** Sections with real content, keyed by id -- everything else falls
 *  through to the honest "not built yet" description below. */
const REAL_SECTION_CONTENT: Partial<Record<string, ComponentType>> = {
  "state-inspector": ModuleStateInspector,
  "voice-state-preview": VoiceStatePreview,
  "startup-preview": StartupPreview,
};

/**
 * The Developer Panel foundation (Task 13). Toggled by Ctrl+Shift+D
 * (providers/developer-provider.tsx). Most sections still honestly show
 * "not built yet" -- real content requires the backend Runtime Manager,
 * WebSocket log relay, and Plugin Platform API (all M9 scope). Three
 * sections are real today because what they drive has no backend
 * dependency: State Inspector reads `ApplicationRegistry` directly
 * (Task 16); Voice State Preview (Phase 4, Task Group H) drives the
 * real `useVoiceStateStore`; Startup Preview (Phase 4, Task Group I)
 * replays the real startup sequence.
 */
export function DeveloperPanel() {
  const activePanelId = useDeveloperModeStore((s) => s.activePanelId);
  const setActivePanel = useDeveloperModeStore((s) => s.setActivePanel);
  const isOpen = activePanelId !== null;
  const activeSection =
    DEVELOPER_PANEL_SECTIONS.find((s) => s.id === activePanelId) ?? DEVELOPER_PANEL_SECTIONS[0];

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.aside
          role="dialog"
          aria-label="Developer Panel"
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ duration: MOTION_DURATIONS.slow / 1000, ease: "easeOut" }}
          className="fixed inset-y-0 right-0 z-50 flex w-96 max-w-full border-border border-l bg-card shadow-elevation-high"
        >
          <nav
            aria-label="Developer Panel sections"
            className="flex w-14 flex-col items-center gap-1 border-border border-r py-3"
          >
            {DEVELOPER_PANEL_SECTIONS.map((section) => (
              <button
                key={section.id}
                type="button"
                aria-label={section.label}
                aria-current={activeSection.id === section.id ? "true" : undefined}
                onClick={() => setActivePanel(section.id)}
                className={cn(
                  "flex size-10 items-center justify-center rounded-lg transition-colors duration-fast",
                  "hover:bg-accent/10 hover:text-accent focus-visible:outline-2 focus-visible:outline-ring",
                  activeSection.id === section.id
                    ? "bg-accent/15 text-accent"
                    : "text-muted-foreground",
                )}
              >
                <section.icon className="size-icon-md" aria-hidden="true" />
              </button>
            ))}
          </nav>

          <div className="flex flex-1 flex-col">
            <div className="flex items-center justify-between border-border border-b px-4 py-3">
              <div className="flex items-center gap-2">
                <Lock className="size-icon-sm text-muted-foreground" aria-hidden="true" />
                <h2 className="text-widget-title font-semibold">{activeSection.label}</h2>
              </div>
              <button
                type="button"
                aria-label="Close Developer Panel"
                onClick={() => setActivePanel(null)}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-accent/10 hover:text-accent"
              >
                <X className="size-icon-sm" aria-hidden="true" />
              </button>
            </div>

            {(() => {
              const RealContent = REAL_SECTION_CONTENT[activeSection.id];
              return RealContent ? (
                <RealContent />
              ) : (
                <div className="flex flex-1 items-center justify-center p-6 text-center">
                  <p className="text-secondary text-muted-foreground">{activeSection.description}</p>
                </div>
              );
            })()}
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
