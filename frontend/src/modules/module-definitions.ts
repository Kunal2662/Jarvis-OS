import type { ModuleManifest } from "@/core/module-manifest";

/**
 * The 14 workspace module manifests -- the `ApplicationRegistry`-driven
 * replacement for the static array in `routes/nav-items.ts`. Same 14
 * modules, same ids (kebab-cased where nav-items.ts's id wasn't already),
 * same routes, same icons, ported 1:1 from that file, not redesigned.
 * This array is now the authoritative source of module data; Sidebar/Dock
 * still read `nav-items.ts` directly until they're rewritten to be
 * registry-driven, at which point that file retires.
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
 * `"local"` for everything else -- pure local state or a local tool with
 * no external account concept.
 */

interface ModuleDefinitionInput {
  name: string;
  displayName: string;
  icon: string;
  route: string;
  category?: ModuleManifest["category"];
}

function definition({ name, displayName, icon, route, category = "local" }: ModuleDefinitionInput): ModuleManifest {
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
    developerMetadata: { author: "JARVIS OS", homepage: null, repository: null },
  };
}

export const MODULE_DEFINITIONS: ModuleManifest[] = [
  definition({ name: "home", displayName: "Home", icon: "home", route: "/" }),
  definition({ name: "chat", displayName: "Chat", icon: "sparkles", route: "/chat" }),
  definition({ name: "voice", displayName: "Voice", icon: "mic", route: "/voice" }),
  definition({ name: "memory", displayName: "Memory", icon: "zap", route: "/memory" }),
  definition({ name: "automations", displayName: "Automations", icon: "workflow", route: "/automations" }),
  definition({ name: "files", displayName: "Files & Drive", icon: "folder-open", route: "/files" }),
  definition({ name: "browser", displayName: "Browser", icon: "globe", route: "/browser" }),
  definition({ name: "coding", displayName: "Coding", icon: "code-2", route: "/coding" }),
  definition({
    name: "finance",
    displayName: "Finance",
    icon: "wallet",
    route: "/finance",
    category: "connected",
  }),
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
  definition({ name: "settings", displayName: "Settings", icon: "settings", route: "/settings" }),
];
