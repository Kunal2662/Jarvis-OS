import { BaseApplication } from "@/core/base-application";
import type { ModuleManifest } from "@/core/module-manifest";

/**
 * A module whose real business logic hasn't shipped yet -- every one of
 * the 14 workspace entries ported from the PySide6-era sidebar (Phase 1's
 * `routes/nav-items.ts`) starts life as one of these. `BaseApplication`'s
 * lifecycle hooks are intentionally left at their no-op defaults: there is
 * no real work to start, pause, or stop yet, so overriding them with
 * placeholder behavior would be exactly the kind of fake implementation
 * this milestone's rules forbid. A module "graduates" out of this class by
 * becoming its own dedicated `BaseApplication` subclass once it ships real
 * logic -- this class is never extended further, only replaced per module.
 */
export class PlaceholderModule extends BaseApplication {
  readonly manifest: ModuleManifest;

  constructor(manifest: ModuleManifest) {
    super();
    this.manifest = manifest;
  }
}
