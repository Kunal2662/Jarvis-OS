import type { LucideIcon } from "lucide-react";
import { Activity, Blocks, Bug, ScrollText, SquareTerminal, Store } from "lucide-react";

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
];
