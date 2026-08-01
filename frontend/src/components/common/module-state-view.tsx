import type { LucideIcon } from "lucide-react";
import { Inbox, Key, Lock, Settings2, TriangleAlert, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/common/loading-spinner";
import type { ViewState } from "@/core/error-framework";

interface ModuleStateViewProps {
  state: ViewState;
  moduleName: string;
  /** Rendered only when `state === "ready"` -- every other state
   *  renders its own standardized screen instead of `children`, so a
   *  module can never accidentally render real content over a
   *  not-actually-ready state. */
  children?: React.ReactNode;
  onRetry?: () => void;
  onConfigure?: () => void;
}

const STATE_COPY: Record<
  Exclude<ViewState, "loading" | "ready">,
  { icon: LucideIcon; title: string; description: (moduleName: string) => string }
> = {
  empty: {
    icon: Inbox,
    title: "Nothing here yet",
    description: (name) => `${name} hasn't received any data yet.`,
  },
  offline: {
    icon: WifiOff,
    title: "Offline",
    description: (name) => `${name} can't reach the backend right now.`,
  },
  error: {
    icon: TriangleAlert,
    title: "Something went wrong",
    description: (name) => `${name} ran into an error.`,
  },
  permission_denied: {
    icon: Lock,
    title: "Permission required",
    description: (name) => `${name} needs a permission you haven't granted yet.`,
  },
  auth_required: {
    icon: Key,
    title: "Sign-in required",
    description: (name) => `${name} needs you to authenticate before it can connect.`,
  },
  config_required: {
    icon: Settings2,
    title: "Setup required",
    description: (name) => `${name} hasn't been configured yet.`,
  },
};

/**
 * The one component every module renders its non-ready states through
 * (Task 13) -- picks its screen from `deriveViewState()`
 * (core/error-framework.ts), never from ad-hoc per-module conditionals.
 */
export function ModuleStateView({ state, moduleName, children, onRetry, onConfigure }: ModuleStateViewProps) {
  if (state === "loading") {
    return <LoadingState label={`Loading ${moduleName}`} />;
  }
  if (state === "ready") {
    return children;
  }

  const copy = STATE_COPY[state];
  const showRetry = (state === "offline" || state === "error") && onRetry;
  const showConfigure = (state === "config_required" || state === "auth_required") && onConfigure;

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <copy.icon className="size-icon-xl text-muted-foreground" aria-hidden="true" />
      <p className="text-card-title font-bold">{copy.title}</p>
      <p className="max-w-sm text-secondary text-muted-foreground">{copy.description(moduleName)}</p>
      {showRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
      {showConfigure && (
        <Button variant="outline" size="sm" onClick={onConfigure}>
          Configure
        </Button>
      )}
    </div>
  );
}
