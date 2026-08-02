import {
  Calendar,
  Code2,
  FolderOpen,
  Globe,
  HelpCircle,
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
  type LucideIcon,
} from "lucide-react";

/**
 * Resolves a `ModuleManifest.icon` string (`ARCHITECTURE.md` section 10's
 * "Lucide icon key, matching the existing IconRegistry pattern") to its
 * real Lucide component. The single place this mapping exists -- every
 * consumer of manifest icon data (Sidebar today; Dock, Command Palette,
 * Developer Mode later) resolves through this file, never importing a
 * `lucide-react` icon against a manifest string itself, so there is
 * exactly one icon key -> component table for the whole app.
 *
 * Keys match `modules/module-definitions.ts`'s existing icon strings
 * exactly (Lucide's own kebab-case slug per icon, e.g. `Code2` ->
 * `"code-2"`). `HelpCircle` is the fallback for an unmapped key -- an
 * internal-bug indicator (every first-party manifest's icon is declared
 * here), not user-facing data, and deliberately non-fatal: one bad icon
 * key must never crash the whole Sidebar.
 */
const ICON_REGISTRY: Record<string, LucideIcon> = {
  home: Home,
  sparkles: Sparkles,
  mic: Mic,
  zap: Zap,
  workflow: Workflow,
  "folder-open": FolderOpen,
  globe: Globe,
  "code-2": Code2,
  wallet: Wallet,
  lightbulb: Lightbulb,
  calendar: Calendar,
  mail: Mail,
  music: Music,
  settings: Settings,
};

export function resolveIcon(iconKey: string): LucideIcon {
  return ICON_REGISTRY[iconKey] ?? HelpCircle;
}
