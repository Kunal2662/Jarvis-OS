/**
 * BaseApplication (Task 1) -- every future JARVIS module (Gmail,
 * Calendar, Spotify, Browser, Memory, Tasks, Finance, Smart Home,
 * Files, AI Chat, ...) extends this class. It is a template-method base
 * class: this file owns the generic lifecycle wiring (state machine
 * transitions, framework instances, registry interaction) that is
 * identical for every module, and exposes `protected onX()` hooks a
 * concrete module overrides for whatever is actually specific to it.
 * `BaseApplication` itself implements zero business logic and knows
 * nothing about any concrete module -- per this phase's explicit rule,
 * "Applications are NOT React pages," this class has no React import at
 * all; a module's React view reads its state through hooks (a later
 * phase), it doesn't extend this class itself.
 *
 * Lifecycle stage responsibilities:
 *
 * | Stage        | Responsibility |
 * |--------------|----------------|
 * | `initialize` | Construct this module's framework instances (storage, settings, API client) and register with the `ApplicationRegistry`. No network I/O, no UI. |
 * | `configure`  | Load and validate this module's settings (Settings Framework) -- callable again later when settings change, not just once at startup. |
 * | `mount`      | The module's route/view entered the React tree -- registers its Navigation contribution (Sidebar/Dock/Command Palette/shortcuts). Not "start working," just "became visible." |
 * | `unmount`    | The inverse of `mount` -- unregisters navigation. Does NOT stop background work; a module can keep syncing while its view isn't visible. |
 * | `start`      | Begin real work -- open API/WebSocket subscriptions, transition the lifecycle state machine toward `connecting`/`ready`. May fail; a failed `start()` transitions to `error`, never throws past this method uncaught. |
 * | `pause`      | Suspend non-critical background work (polling, sync) without losing state -- must be resumable via `resume()` without re-running `start()`. |
 * | `resume`     | Reverses `pause()` exactly. |
 * | `stop`       | Full stop -- closes subscriptions, transitions toward `disconnected`. Safe to call even if `start()` never completed. |
 * | `shutdown`   | The whole app is closing -- transitions the lifecycle to the terminal `shutdown` state. Idempotent. |
 * | `health`     | Cheap, frequent, boolean-ish signal -- matches the backend `IService.health()` shape (ARCHITECTURE.md section 8), applied to the frontend module. |
 * | `status`     | Detailed, on-demand snapshot for Developer Mode (Task 16) -- never polled on a tight loop. |
 * | `dispose`    | Final resource release (event listeners, timers) after `shutdown` -- irreversible; the instance is not reused after this. |
 */

import {
  applicationRegistry,
  DuplicateModuleError,
  type RegisterableApplication,
} from "@/core/application-registry";
import { createModuleApiClient, type ModuleApiClient } from "@/core/interfaces/api-interface";
import { createWindowInterface, type WindowInterface } from "@/core/interfaces/window-interface";
import {
  registerNavigation,
  type NavigationContribution,
} from "@/core/interfaces/navigation-interface";
import { defaultStateFor, type ModuleManifest } from "@/core/module-manifest";
import { ModuleLifecycle, type ConnectionState, type ModuleState } from "@/core/module-lifecycle";
import { permissionFramework, type PermissionFramework } from "@/core/permission-framework";
import { ModuleSettings } from "@/core/settings-framework";
import { getModuleStorage, type ModuleStorage } from "@/core/storage-framework";

export interface ModuleHealth {
  healthy: boolean;
  state: ConnectionState;
}

export interface ModuleStatus {
  moduleId: string;
  state: ModuleState;
  history: readonly ModuleState[];
  permissions: ReturnType<PermissionFramework["getGrantsFor"]>;
}

export abstract class BaseApplication implements RegisterableApplication {
  abstract readonly manifest: ModuleManifest;

  protected lifecycle!: ModuleLifecycle;
  protected api!: ModuleApiClient;
  protected storage!: ModuleStorage;
  protected settings!: ModuleSettings;
  protected windowInterface!: WindowInterface;

  private unregisterNavigation: (() => void) | null = null;
  private disposed = false;

  // --- Lifecycle (Task 1) --------------------------------------------------

  async initialize(): Promise<void> {
    this.lifecycle = new ModuleLifecycle(this.manifest.name, defaultStateFor(this.manifest));
    this.api = createModuleApiClient(this.manifest.name);
    this.storage = getModuleStorage(this.manifest.name);
    this.settings = new ModuleSettings(this.manifest.name, this.manifest.settingsSchema);
    this.windowInterface = createWindowInterface(this.manifest.name);

    try {
      applicationRegistry.register(this);
    } catch (error) {
      if (!(error instanceof DuplicateModuleError)) throw error;
    }

    await this.onInitialize();
  }

  async configure(): Promise<void> {
    await this.onConfigure();
  }

  mount(): void {
    this.unregisterNavigation = registerNavigation(this.getNavigationContribution());
    this.onMount();
  }

  unmount(): void {
    this.unregisterNavigation?.();
    this.unregisterNavigation = null;
    this.onUnmount();
  }

  async start(): Promise<void> {
    try {
      await this.onStart();
    } catch (error) {
      this.lifecycle.transitionTo("error", { error: error instanceof Error ? error.message : String(error) });
      throw error;
    }
  }

  async pause(): Promise<void> {
    await this.onPause();
  }

  async resume(): Promise<void> {
    await this.onResume();
  }

  async stop(): Promise<void> {
    await this.onStop();
    if (this.lifecycle.canTransitionTo("disconnected")) {
      this.lifecycle.transitionTo("disconnected");
    }
  }

  async shutdown(): Promise<void> {
    if (this.lifecycle.state === "shutdown") return; // idempotent
    await this.onShutdown();
    this.lifecycle.transitionTo("shutdown");
  }

  dispose(): void {
    if (this.disposed) return; // idempotent
    this.unregisterNavigation?.();
    this.onDispose();
    this.disposed = true;
  }

  // --- Diagnostics (Task 1, consumed by Task 16) ---------------------------

  health(): ModuleHealth {
    return {
      healthy: !["error", "offline", "shutdown"].includes(this.lifecycle.state),
      state: this.lifecycle.state,
    };
  }

  status(): ModuleStatus {
    return {
      moduleId: this.manifest.name,
      state: this.lifecycle.moduleState,
      history: this.lifecycle.getHistory(),
      permissions: permissionFramework.getGrantsFor(this.manifest.name),
    };
  }

  // --- Overridable hooks -- every concrete module fills these in, never
  //     the lifecycle methods above directly. No-op by default so a
  //     module only implements what it actually needs. ---------------------

  protected async onInitialize(): Promise<void> {}
  protected async onConfigure(): Promise<void> {}
  protected onMount(): void {}
  protected onUnmount(): void {}
  protected async onStart(): Promise<void> {}
  protected async onPause(): Promise<void> {}
  protected async onResume(): Promise<void> {}
  protected async onStop(): Promise<void> {}
  protected async onShutdown(): Promise<void> {}
  protected onDispose(): void {}

  /** Overridden by a module that wants Sidebar/Dock/Command
   *  Palette/shortcut participation (Task 15) -- the default
   *  contribution is inert (nothing registered) so a module without
   *  navigation needs does not have to override this. */
  protected getNavigationContribution(): NavigationContribution {
    return {
      moduleId: this.manifest.name,
      sidebarVisible: false,
      dockEligible: false,
      commandPaletteEntries: [],
      searchable: false,
      keyboardShortcuts: [],
    };
  }
}
