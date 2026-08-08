import { useMemo } from "react";
import { Bell, BellOff, Check, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { VirtualList } from "@/components/common/virtual-list";
import { useNotificationsStore, type NotificationRecord } from "@/stores/notifications.store";

/**
 * The Notification Center -- the persistent panel view over
 * `core/notification-framework.ts`'s already-real data.
 *
 * Listed in `IMPLEMENTATION_ROADMAP.md` §2 Phase 3 and moved to the
 * Deferred Backlog because it needed a container to live in;
 * `components/layout/notification-layer.tsx` has been a reserved
 * `return null` anchor since Phase 1. The panel framework is that
 * container, so it ships here.
 *
 * **Distinct from the toast surface, not a duplicate of it.**
 * `providers/notification-provider.tsx` renders ephemeral toasts; this
 * is the list that is still there after a toast has gone. Both read the
 * same store, which is why an entry cannot appear in one and not the
 * other.
 *
 * Every row is real: entries arrive from `notificationFramework.*()` or
 * from the backend's `notification.plugin` WebSocket event via
 * `services/realtime-bridge.ts`. Nothing is seeded.
 */

const SEVERITY_STYLES: Record<NotificationRecord["severity"], string> = {
  info: "bg-primary/15 text-primary",
  success: "bg-emerald-500/15 text-emerald-500",
  warning: "bg-amber-500/15 text-amber-500",
  error: "bg-destructive/15 text-destructive",
};

function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function NotificationRow({ item }: { item: NotificationRecord }) {
  const markRead = useNotificationsStore((s) => s.markRead);

  return (
    <li
      className={`flex gap-3 border-border/60 border-b px-3 py-2.5 ${item.read ? "opacity-60" : ""}`}
    >
      <span
        className={`mt-0.5 size-2 shrink-0 rounded-full ${SEVERITY_STYLES[item.severity]}`}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <p className="truncate font-medium text-secondary">{item.title}</p>
          <time className="shrink-0 text-muted-foreground text-xs" dateTime={item.createdAt}>
            {formatTime(item.createdAt)}
          </time>
        </div>
        <p className="text-muted-foreground text-xs">{item.message}</p>
      </div>
      {!item.read && (
        <Button
          variant="ghost"
          size="icon"
          className="size-6 shrink-0"
          aria-label={`Mark "${item.title}" as read`}
          onClick={() => markRead(item.id)}
        >
          <Check className="size-3.5" aria-hidden="true" />
        </Button>
      )}
    </li>
  );
}

export function NotificationCenter() {
  const items = useNotificationsStore((s) => s.items);
  const clear = useNotificationsStore((s) => s.clear);
  const markRead = useNotificationsStore((s) => s.markRead);

  const unread = useMemo(() => items.filter((item) => !item.read), [items]);

  if (items.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
        <BellOff className="size-icon-lg text-muted-foreground" aria-hidden="true" />
        <p className="font-medium text-secondary">No notifications</p>
        <p className="max-w-xs text-muted-foreground text-xs">
          Alerts from JARVIS and its modules appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 border-border/60 border-b px-3 py-2">
        <span className="flex items-center gap-1.5 text-muted-foreground text-xs">
          <Bell className="size-3.5" aria-hidden="true" />
          {unread.length > 0 ? `${unread.length} unread` : "All read"}
        </span>
        <div className="flex gap-1">
          {unread.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-xs"
              onClick={() => {
                for (const item of unread) markRead(item.id);
              }}
            >
              Mark all read
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="size-6"
            aria-label="Clear all notifications"
            onClick={clear}
          >
            <Trash2 className="size-3.5" aria-hidden="true" />
          </Button>
        </div>
      </div>
      {/* Virtualised: the store is unbounded, and a long-running session
          can accumulate hundreds of entries behind a panel that is
          often open. */}
      <VirtualList
        items={items}
        estimatedItemHeight={64}
        className="min-h-0 flex-1"
        renderItem={(item) => <NotificationRow key={item.id} item={item} />}
      />
    </div>
  );
}
