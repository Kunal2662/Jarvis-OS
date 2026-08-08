import type { ReactNode } from "react";
import { Inbox, RotateCw, TriangleAlert, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SkeletonRows, SkeletonStatGrid } from "@/components/common/skeleton";
import type { ResourceState } from "@/hooks/use-backend-resource";

/**
 * Renders a `ResourceState` -- the one place loading, empty, offline and
 * error look the way they look (M8 Phase 6).
 *
 * Pairs with `useBackendResource`: that hook decides *which* state is
 * true, this component decides what each one looks like. Splitting them
 * means a widget can reuse the states without the fetch (the health
 * widgets read a store, not a request) and vice versa.
 *
 * Related to but distinct from `components/common/module-state-view.tsx`,
 * which renders a whole *module's* lifecycle state at full-screen size.
 * This is the inside of a dashboard widget: smaller, quieter, and
 * skeleton-first rather than spinner-first, because a widget's layout is
 * known in advance and a skeleton in a known shape does not make the
 * grid jump when the data lands.
 */

interface ResourceViewProps<T> {
  state: ResourceState<T>;
  children: (data: T) => ReactNode;
  /** What the skeleton should look like — match it to the content. */
  skeleton?: "rows" | "stats" | "none";
  skeletonRows?: number;
  /** Named for the screen-reader announcement and the empty state. */
  label: string;
  emptyMessage?: string;
  onRetry?: () => void;
}

export function ResourceView<T>({
  state,
  children,
  skeleton = "rows",
  skeletonRows = 3,
  label,
  emptyMessage,
  onRetry,
}: ResourceViewProps<T>) {
  if (state.status === "ready") return <>{children(state.data)}</>;

  if (state.status === "idle" || state.status === "loading") {
    if (skeleton === "none") return null;
    return skeleton === "stats" ? (
      <SkeletonStatGrid label={`Loading ${label}`} />
    ) : (
      <SkeletonRows rows={skeletonRows} label={`Loading ${label}`} />
    );
  }

  if (state.status === "offline") {
    return (
      <Message
        icon={<WifiOff className="size-icon-md text-muted-foreground" aria-hidden="true" />}
        title="Offline"
        detail={`${label} needs the JARVIS backend, which isn't reachable right now.`}
      />
    );
  }

  if (state.status === "empty") {
    return (
      <Message
        icon={<Inbox className="size-icon-md text-muted-foreground" aria-hidden="true" />}
        title="Nothing yet"
        detail={emptyMessage ?? `No ${label.toLowerCase()} to show.`}
      />
    );
  }

  return (
    <Message
      icon={<TriangleAlert className="size-icon-md text-muted-foreground" aria-hidden="true" />}
      title="Couldn't load"
      detail={state.message}
      action={
        onRetry && (
          <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs" onClick={onRetry}>
            <RotateCw className="size-3" aria-hidden="true" />
            Retry
          </Button>
        )
      }
    />
  );
}

function Message({
  icon,
  title,
  detail,
  action,
}: {
  icon: ReactNode;
  title: string;
  detail: string;
  action?: ReactNode;
}) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-1.5 p-6 text-center"
      // `status` not `alert`: a widget that could not load is worth
      // announcing politely, but it must not interrupt whatever the user
      // is doing elsewhere on the dashboard.
      role="status"
    >
      {icon}
      <p className="font-medium text-secondary">{title}</p>
      <p className="max-w-xs text-muted-foreground text-xs">{detail}</p>
      {action}
    </div>
  );
}
