import type { LucideIcon } from "lucide-react";
import { Activity, AudioLines, Blocks, Bug, Rocket, ScrollText, SquareTerminal, Store } from "lucide-react";

export interface DeveloperPanelSection {
  id: string;
  label: string;
  icon: LucideIcon;
  description: string;
}

/**
 * The 6 Developer Platform Tools sections defined in ARCHITECTURE.md
 * section 10 (M9's "Developer Platform Tools" module) -- empty
 * placeholders only, per this phase's explicit "no functionality" rule.
 * Each section becomes real once its own backend counterpart exists
 * (Runtime Manager's Service Registry, the WebSocket log relay, etc.).
 */
export const DEVELOPER_PANEL_SECTIONS: DeveloperPanelSection[] = [
  {
    id: "overview",
    label: "Overview",
    icon: Activity,
    description: "Runtime status summary -- populated once the Runtime Manager (M9) exists.",
  },
  {
    id: "debug-console",
    label: "Debug Console",
    icon: SquareTerminal,
    description: "Live, filterable structured logs -- streamed once the WebSocket log relay exists.",
  },
  {
    id: "live-logs",
    label: "Live Logs",
    icon: ScrollText,
    description: "Same live stream as Debug Console, tailored for the Agent/Voice/Automation event categories.",
  },
  {
    id: "performance-profiler",
    label: "Performance Profiler",
    icon: Bug,
    description: "Per-service resource usage -- surfaces Resource Manager's data once M9 ships it.",
  },
  {
    id: "state-inspector",
    label: "State Inspector",
    icon: Blocks,
    description: "Live view into each service's ModuleStateMachine state (ARCHITECTURE.md section 4).",
  },
  {
    id: "plugin-marketplace",
    label: "Plugin Marketplace",
    icon: Store,
    description: "Backend index/install/uninstall UI -- renders once M9's Plugin Platform API exists.",
  },
  {
    id: "voice-state-preview",
    label: "Voice State Preview",
    icon: AudioLines,
    // Unlike every section above, this one IS real today -- it drives
    // the real `useVoiceStateStore` (Phase 4, Task Group H), the same
    // one a real voice pipeline will call `transition()` on once it
    // exists. Kept in this list (Developer Mode-gated, off by default)
    // rather than shipped as a real end-user surface, since manually
    // forcing voice states has no legitimate end-user use case.
    description: "Manually drive or auto-cycle the real voice state machine, for animation QA.",
  },
  {
    id: "startup-preview",
    label: "Startup Preview",
    icon: Rocket,
    // Also real (Phase 4, Task Group I) -- replays the actual
    // `StartupSequence` component the app plays once per real launch,
    // and toggles the real `accessibility-preferences.store.ts` flags.
    // Settings > Accessibility (Task Group K) is now the real
    // end-user-facing surface for these same three preferences; this
    // panel stays as the QA-only sequence replay plus a developer
    // shortcut to the same toggles, not a duplicate source of truth.
    description: "Replay the real startup sequence, and toggle skip/motion/glass-effect preferences, for QA.",
  },
];
