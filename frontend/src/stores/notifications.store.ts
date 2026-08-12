import { create } from "zustand";

export interface NotificationRecord {
  id: string;
  title: string;
  message: string;
  severity: "info" | "warning" | "error" | "success";
  createdAt: string;
  read: boolean;
}

interface NotificationsState {
  items: NotificationRecord[];
  /** Populated by the `notification.plugin` WebSocket event, via
   *  `services/realtime-bridge.ts` -- never fabricated client-side.
   *  (Phase 1's comment here named `notification.created`, which no
   *  backend event has ever been; corrected in M8 Phase 2 along with the
   *  rest of the invented event vocabulary.) */
  add: (item: NotificationRecord) => void;
  markRead: (id: string) => void;
  clear: () => void;
  unreadCount: () => number;
}

/**
 * The persistent notification center list -- distinct from ephemeral
 * toasts (rendered directly via shadcn/ui's `sonner`, no store needed for
 * those). Not persisted to localStorage: this list's source of truth is
 * the backend once M8's WebSocket layer is real; until then it starts
 * empty, never seeded with placeholder data.
 */
export const useNotificationsStore = create<NotificationsState>()((set, get) => ({
  items: [],
  add: (item) => set((s) => ({ items: [item, ...s.items] })),
  markRead: (id) =>
    set((s) => ({ items: s.items.map((n) => (n.id === id ? { ...n, read: true } : n)) })),
  clear: () => set({ items: [] }),
  unreadCount: () => get().items.filter((n) => !n.read).length,
}));
