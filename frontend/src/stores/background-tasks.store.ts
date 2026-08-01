import { create } from "zustand";

export interface BackgroundTask {
  id: string;
  moduleId: string;
  label: string;
  percent: number | null; // null = indeterminate
  status: "running" | "completed" | "failed";
}

interface BackgroundTasksState {
  tasks: BackgroundTask[];
  start: (task: Omit<BackgroundTask, "status">) => void;
  update: (id: string, percent: number, label?: string) => void;
  complete: (id: string) => void;
  fail: (id: string) => void;
}

/**
 * UI state only -- tracks in-flight long-running operations (backups,
 * cloud sync, bulk imports) for the Notification Framework's Progress
 * category (Task 8) to render. A task's real progress comes from the
 * `progress.update` WebSocket event (ARCHITECTURE.md section 6) once a
 * backend exists to publish it; this store never fabricates progress.
 */
export const useBackgroundTasksStore = create<BackgroundTasksState>()((set) => ({
  tasks: [],
  start: (task) => set((s) => ({ tasks: [...s.tasks, { ...task, status: "running" }] })),
  update: (id, percent, label) =>
    set((s) => ({
      tasks: s.tasks.map((t) => (t.id === id ? { ...t, percent, label: label ?? t.label } : t)),
    })),
  complete: (id) =>
    set((s) => ({ tasks: s.tasks.map((t) => (t.id === id ? { ...t, status: "completed" } : t)) })),
  fail: (id) => set((s) => ({ tasks: s.tasks.map((t) => (t.id === id ? { ...t, status: "failed" } : t)) })),
}));
