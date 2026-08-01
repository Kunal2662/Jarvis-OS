import { Toaster } from "@/components/ui/sonner";

/**
 * Renders shadcn/ui's toast surface for ephemeral notifications (a
 * REST/WebSocket action's immediate result -- "Saved", "Connection
 * lost"). The persistent notification *center* list is a separate
 * concern (`stores/notifications.store.ts`), rendered by a future
 * Notification Center component, not this provider.
 */
export function NotificationProvider({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <Toaster position="bottom-right" />
    </>
  );
}
