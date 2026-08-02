import type { ModuleManifest } from "@/core/module-manifest";

/**
 * The 14 workspace module manifests -- the `ApplicationRegistry`-driven
 * replacement for the static array in `routes/nav-items.ts`. This array
 * is the authoritative source of module data; `routes/router.tsx` and
 * `components/layout/header.tsx` both read from here now, not
 * `nav-items.ts` -- the only remaining reader is `components/layout/dock.tsx`,
 * whose own rewrite is Task Group D's job, not this one's.
 *
 * Every optional field below (permissions, commands, voiceCommands,
 * automationSupport, settingsSchema, capabilities) is deliberately empty:
 * none of these 14 modules has real behavior yet, and declaring a
 * capability or permission a module doesn't actually use would be exactly
 * the kind of hardcoded future assumption this milestone's rules forbid.
 * Each field is populated only when the module it describes actually
 * ships that behavior.
 *
 * `smart-home` uses a hyphen here even though `nav-items.ts`'s id is
 * `smart_home` -- `ModuleManifest.name` must satisfy `module-manifest.ts`'s
 * kebab-case validator, which nav-items.ts's id (written before that
 * validator existed) was never checked against. The route path was
 * already `/smart-home`; this just brings the module id in line with it
 * and with every other module's naming.
 *
 * `category` follows `module-manifest.ts`'s own definition: `"connected"`
 * for an external, authenticated account (Gmail, Calendar, Spotify --
 * Google Workspace/OAuth per MASTER_ROADMAP.md's M11), Finance and Smart
 * Home (external providers/paired devices per M11 and M12), and
 * `"local"` for everything else.
 *
 * `isCore`/`parentGroup` (UI Architecture Update, Aug 2026): the 7 core
 * modules (Dashboard, AI's three children, Automation, Files, Settings)
 * ship enabled and cannot be disabled; the other 7 (Browser, Coding,
 * Finance, Smart Home, Calendar, Gmail, Spotify) ship disabled by
 * default and only appear once a user enables them (Settings ->
 * Plugins, Phase 5) -- see `stores/module-enablement.store.ts`. A few
 * display labels changed to match the approved minimal taxonomy
 * exactly (Home -> Dashboard, Chat -> Conversation, Automations ->
 * Automation, "Files & Drive" -> Files); ids, routes, and icons are
 * unchanged.
 */

interface ModuleDefinitionInput {
  name: string;
  displayName: string;
  icon: string;
  route: string;
  category?: ModuleManifest["category"];
  isCore?: boolean;
  parentGroup?: string;
}

function definition({
  name,
  displayName,
  icon,
  route,
  category = "local",
  isCore = false,
  parentGroup,
}: ModuleDefinitionInput): ModuleManifest {
  return {
    name,
    displayName,
    version: "1.0.0",
    category,
    dependencies: [],
    permissions: [],
    commands: [],
    voiceCommands: [],
    automationSupport: { actions: [], reversible: [] },
    settingsSchema: {},
    icon,
    routes: [route],
    capabilities: [],
    isCore,
    parentGroup,
    developerMetadata: { author: "JARVIS OS", homepage: null, repository: null },
  };
}

export const MODULE_DEFINITIONS: ModuleManifest[] = [
  // --- Core (always enabled, cannot be disabled) --------------------------
  definition({ name: "home", displayName: "Dashboard", icon: "home", route: "/", isCore: true }),
  definition({
    name: "chat",
    displayName: "Conversation",
    icon: "sparkles",
    route: "/chat",
    isCore: true,
    parentGroup: "ai",
  }),
  definition({ name: "voice", displayName: "Voice", icon: "mic", route: "/voice", isCore: true, parentGroup: "ai" }),
  definition({
    name: "memory",
    displayName: "Memory",
    icon: "zap",
    route: "/memory",
    isCore: true,
    parentGroup: "ai",
  }),
  definition({
    name: "automations",
    displayName: "Automation",
    icon: "workflow",
    route: "/automations",
    isCore: true,
  }),
  definition({ name: "files", displayName: "Files", icon: "folder-open", route: "/files", isCore: true }),
  definition({ name: "settings", displayName: "Settings", icon: "settings", route: "/settings", isCore: true }),

  // --- Optional (disabled by default, enable via Settings -> Plugins) -----
  definition({ name: "browser", displayName: "Browser", icon: "globe", route: "/browser" }),
  definition({ name: "coding", displayName: "Coding", icon: "code-2", route: "/coding" }),
  definition({ name: "finance", displayName: "Finance", icon: "wallet", route: "/finance", category: "connected" }),
  definition({
    name: "smart-home",
    displayName: "Smart Home",
    icon: "lightbulb",
    route: "/smart-home",
    category: "connected",
  }),
  definition({
    name: "calendar",
    displayName: "Calendar",
    icon: "calendar",
    route: "/calendar",
    category: "connected",
  }),
  definition({ name: "gmail", displayName: "Gmail", icon: "mail", route: "/gmail", category: "connected" }),
  definition({
    name: "spotify",
    displayName: "Spotify",
    icon: "music",
    route: "/spotify",
    category: "connected",
  }),
];
