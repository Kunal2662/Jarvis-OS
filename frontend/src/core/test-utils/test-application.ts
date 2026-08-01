import { BaseApplication } from "@/core/base-application";
import { createTestManifest } from "@/core/test-utils/create-test-manifest";
import type { ModuleManifest } from "@/core/module-manifest";

/**
 * Testing Foundation (Task 17) -- a minimal, concrete `BaseApplication`
 * subclass for exercising the base class's own generic lifecycle
 * behavior in tests, without any real module's business logic. Records
 * every hook call in `calls`, in order, so a test can assert exactly
 * which stages ran. Not a template for a real module (a real module
 * overrides the hooks with actual behavior, not call-recording) --
 * exists solely to test `base-application.ts` itself.
 */
export class TestApplication extends BaseApplication {
  readonly manifest: ModuleManifest;
  readonly calls: string[] = [];

  constructor(manifestOverrides: Partial<ModuleManifest> = {}) {
    super();
    this.manifest = createTestManifest(manifestOverrides);
  }

  protected override async onInitialize(): Promise<void> {
    this.calls.push("onInitialize");
  }
  protected override async onConfigure(): Promise<void> {
    this.calls.push("onConfigure");
  }
  protected override onMount(): void {
    this.calls.push("onMount");
  }
  protected override onUnmount(): void {
    this.calls.push("onUnmount");
  }
  protected override async onStart(): Promise<void> {
    this.calls.push("onStart");
  }
  protected override async onPause(): Promise<void> {
    this.calls.push("onPause");
  }
  protected override async onResume(): Promise<void> {
    this.calls.push("onResume");
  }
  protected override async onStop(): Promise<void> {
    this.calls.push("onStop");
  }
  protected override async onShutdown(): Promise<void> {
    this.calls.push("onShutdown");
  }
  protected override onDispose(): void {
    this.calls.push("onDispose");
  }
}
