import { create } from 'zustand';
import { AvatarState } from '@/components/dex-avatar';
import { ActivityItem } from '@/components/activity-feed';
import { Task } from '@/components/task-card';

/**
 * Store for Dex avatar state
 */
interface DexStore {
  avatarState: AvatarState;
  currentTask: string | null;
  setAvatarState: (state: AvatarState) => void;
  setCurrentTask: (task: string | null) => void;
}

export const useDexStore = create<DexStore>((set) => ({
  avatarState: 'idle',
  currentTask: null,
  setAvatarState: (state) => set({ avatarState: state }),
  setCurrentTask: (task) => set({ currentTask: task }),
}));

/**
 * Store for activity feed
 */
interface ActivityStore {
  items: ActivityItem[];
  isConnected: boolean;
  setItems: (items: ActivityItem[]) => void;
  addItem: (item: ActivityItem) => void;
  setConnected: (connected: boolean) => void;
  clearItems: () => void;
}

export const useActivityStore = create<ActivityStore>((set) => ({
  items: [],
  isConnected: false,
  setItems: (items) => set({ items }),
  addItem: (item) =>
    set((state) => ({
      items: [item, ...state.items].slice(0, 50), // Keep last 50 items
    })),
  setConnected: (connected) => set({ isConnected: connected }),
  clearItems: () => set({ items: [] }),
}));

/**
 * Store for metrics/statistics
 */
interface MetricsStore {
  tasksToday: number;
  messagesToday: number;
  costToday: number;
  updateMetrics: (metrics: Partial<Omit<MetricsStore, 'updateMetrics'>>) => void;
}

export const useMetricsStore = create<MetricsStore>((set) => ({
  tasksToday: 0,
  messagesToday: 0,
  costToday: 0,
  updateMetrics: (metrics) => set((state) => ({ ...state, ...metrics })),
}));

/**
 * Toast notification type
 */
export interface Toast {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  duration?: number;
}

/**
 * Store for toast notifications
 */
interface ToastStore {
  toasts: Toast[];
  addToast: (toast: Omit<Toast, 'id'>) => void;
  removeToast: (id: string) => void;
  clearAll: () => void;
}

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  addToast: (toast) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    const newToast: Toast = { ...toast, id };

    set((state) => ({
      toasts: [...state.toasts, newToast],
    }));

    // Auto-dismiss after duration (default 5 seconds)
    const duration = toast.duration || 5000;
    setTimeout(() => {
      set((state) => ({
        toasts: state.toasts.filter((t) => t.id !== id),
      }));
    }, duration);
  },
  removeToast: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    })),
  clearAll: () => set({ toasts: [] }),
}));

/**
 * Store for tasks page
 */
interface TasksStore {
  tasks: Task[];
  selectedTask: Task | null;
  filters: {
    status?: string;
    channel?: string;
    search?: string;
  };
  setTasks: (tasks: Task[]) => void;
  setSelectedTask: (task: Task | null) => void;
  setFilters: (filters: TasksStore['filters']) => void;
  addTask: (task: Task) => void;
  updateTask: (id: string, updates: Partial<Task>) => void;
}

export const useTasksStore = create<TasksStore>((set) => ({
  tasks: [],
  selectedTask: null,
  filters: {},
  setTasks: (tasks) => set({ tasks }),
  setSelectedTask: (task) => set({ selectedTask: task }),
  setFilters: (filters) => set({ filters }),
  addTask: (task) =>
    set((state) => ({
      tasks: [task, ...state.tasks],
    })),
  updateTask: (id, updates) =>
    set((state) => ({
      tasks: state.tasks.map((t) => (t.id === id ? { ...t, ...updates } : t)),
    })),
}));
