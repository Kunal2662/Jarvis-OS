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
  /** Populated by the `notification.created` WebSocket event (see
   *  services/websocket/) -- never fabricated client-side. */
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
