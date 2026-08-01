/**
 * The Notification Framework -- the one API every module uses to notify
 * the user (Task 8), routing to the right existing surface rather than
 * each module picking its own:
 *
 * - success / error / warning / info  -> ephemeral toast (sonner, via
 *   providers/notification-provider.tsx) AND a persistent entry
 *   (stores/notifications.store.ts) so it's still visible after the
 *   toast disappears.
 * - progress                          -> stores/background-tasks.store.ts,
 *   rendered wherever a future "Background Tasks" panel reads it.
 * - background tasks                  -> same store, `start`/`update`/
 *   `complete`/`fail` lifecycle.
 * - push notifications                -> not implemented; documented
 *   below as the future OS-level hook (Tauri's notification plugin),
 *   per Task 8's own "Future Push Notifications" item -- interface
 *   shaped for it, nothing wired.
 */

import { toast } from "sonner";
import { useBackgroundTasksStore } from "@/stores/background-tasks.store";
import { useNotificationsStore } from "@/stores/notifications.store";
import type { NotificationRecord } from "@/stores/notifications.store";

export type NotificationSeverity = NotificationRecord["severity"];

function notify(moduleId: string, severity: NotificationSeverity, title: string, message: string): void {
  const record: NotificationRecord = {
    id: crypto.randomUUID(),
    title,
    message,
    severity,
    createdAt: new Date().toISOString(),
    read: false,
  };
  useNotificationsStore.getState().add(record);
  toast[severity](title, { description: message });
  void moduleId; // reserved for a future per-module notification-preferences check (Settings Framework)
}

export const notificationFramework = {
  success: (moduleId: string, title: string, message: string) => notify(moduleId, "success", title, message),
  error: (moduleId: string, title: string, message: string) => notify(moduleId, "error", title, message),
  warning: (moduleId: string, title: string, message: string) => notify(moduleId, "warning", title, message),
  info: (moduleId: string, title: string, message: string) => notify(moduleId, "info", title, message),

  progress: {
    start(moduleId: string, id: string, label: string): void {
      useBackgroundTasksStore.getState().start({ id, moduleId, label, percent: null });
    },
    update(id: string, percent: number, label?: string): void {
      useBackgroundTasksStore.getState().update(id, percent, label);
    },
    complete(id: string): void {
      useBackgroundTasksStore.getState().complete(id);
    },
    fail(id: string): void {
      useBackgroundTasksStore.getState().fail(id);
    },
  },

  /**
   * Not implemented -- OS-level push notifications require Tauri's
   * `@tauri-apps/plugin-notification` (not yet a dependency) and, for
   * anything beyond a local reminder, a real backend push service (no
   * such service exists; M11's Integrations & Cloud Platform is the
   * earliest place one could land). Throws deliberately rather than
   * silently no-op-ing, so a future caller finds out immediately that
   * this path isn't real yet, instead of assuming a push notification
   * was sent.
   */
  push(_moduleId: string, _title: string, _message: string): never {
    throw new Error(
      "Push notifications are not implemented. Requires @tauri-apps/plugin-notification " +
        "(OS-level) and/or a backend push service (M11+) -- see notification-framework.ts.",
    );
  },
};
