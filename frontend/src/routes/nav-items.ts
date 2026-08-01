import type { LucideIcon } from "lucide-react";
import {
  Calendar,
  Code2,
  FolderOpen,
  Globe,
  Home,
  Lightbulb,
  Mail,
  Mic,
  Music,
  Settings,
  Sparkles,
  Wallet,
  Workflow,
  Zap,
} from "lucide-react";

export interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
  path: string;
}

/**
 * The 14 workspace nav entries -- ported verbatim (same ids, same order)
 * from the shipped PySide6 sidebar's `_NAV_KEYS`
 * (`src/jarvis/ui/widgets/sidebar.py`), so both frontends agree on what a
 * "module" is while the migration is in progress. Every route below
 * renders the shared placeholder (routes/placeholder-route.tsx) until its
 * real module ships in a later phase -- see MASTER_ROADMAP.md section 8.
 *
 * Transitional status (Phase 3, Task Group A): the authoritative source
 * of module data is now `modules/module-definitions.ts`'s
 * `MODULE_DEFINITIONS`, registered with `ApplicationRegistry`. This file
 * still backs Sidebar/Dock directly until they're rewritten to be
 * registry-driven (Phase 3, Task Groups C/D), at which point it retires.
 * Don't add a 15th entry here without adding it to `MODULE_DEFINITIONS`
 * too -- the two are expected to converge, not diverge.
 */
export const NAV_ITEMS: NavItem[] = [
  { id: "home", label: "Home", icon: Home, path: "/" },
  { id: "chat", label: "Chat", icon: Sparkles, path: "/chat" },
  { id: "voice", label: "Voice", icon: Mic, path: "/voice" },
  { id: "memory", label: "Memory", icon: Zap, path: "/memory" },
  { id: "automations", label: "Automations", icon: Workflow, path: "/automations" },
  { id: "files", label: "Files & Drive", icon: FolderOpen, path: "/files" },
  { id: "browser", label: "Browser", icon: Globe, path: "/browser" },
  { id: "coding", label: "Coding", icon: Code2, path: "/coding" },
  { id: "finance", label: "Finance", icon: Wallet, path: "/finance" },
  { id: "smart_home", label: "Smart Home", icon: Lightbulb, path: "/smart-home" },
  { id: "calendar", label: "Calendar", icon: Calendar, path: "/calendar" },
  { id: "gmail", label: "Gmail", icon: Mail, path: "/gmail" },
  { id: "spotify", label: "Spotify", icon: Music, path: "/spotify" },
  { id: "settings", label: "Settings", icon: Settings, path: "/settings" },
];
