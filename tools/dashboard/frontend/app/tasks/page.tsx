'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  Target,
  Check,
  SkipForward,
  HelpCircle,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  RefreshCw,
  Plus,
  Clock,
  Tag,
  AlertCircle,
  X,
  Loader2,
  ListTree,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { EnergyIndicator, EnergyLevel } from '@/components/energy-selector';
import { api, FrictionItem } from '@/lib/api';

interface Task {
  id: string;
  title: string;
  description?: string;
  status: 'pending' | 'in_progress' | 'completed' | 'skipped';
  energyRequired: EnergyLevel;
  estimatedTime?: string;
  category?: string;
  source?: string;
  createdAt: Date;
  completedAt?: Date;
}

interface Subtask {
  title: string;
  energy?: string;
  description?: string;
}

const isDemo = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

// Demo data (fallback)
const demoTasks: Task[] = [
  {
    id: '1',
    title: 'Reply to Sarah\'s email about the Q4 report',
    description: 'She asked for the updated projections by end of day',
    status: 'pending',
    energyRequired: 'low',
    estimatedTime: '5 min',
    category: 'Email',
    createdAt: new Date(Date.now() - 2 * 60 * 60 * 1000),
  },
  {
    id: '2',
    title: 'Review budget spreadsheet',
    status: 'pending',
    energyRequired: 'medium',
    estimatedTime: '15 min',
    category: 'Finance',
    createdAt: new Date(Date.now() - 4 * 60 * 60 * 1000),
  },
  {
    id: '3',
    title: 'Call Mike about project timeline',
    status: 'pending',
    energyRequired: 'high',
    estimatedTime: '20 min',
    category: 'Meetings',
    createdAt: new Date(Date.now() - 6 * 60 * 60 * 1000),
  },
  {
    id: '4',
    title: 'Submit expense report',
    status: 'completed',
    energyRequired: 'low',
    category: 'Admin',
    createdAt: new Date(Date.now() - 24 * 60 * 60 * 1000),
    completedAt: new Date(Date.now() - 2 * 60 * 60 * 1000),
  },
];

const demoFriction: FrictionItem[] = [
  {
    task_id: '3',
    task_title: 'Call Mike',
    blocker: 'Mike\'s phone number needed',
    suggested_action: 'Search in contacts',
    confidence: 0.85,
  },
];

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [friction, setFriction] = useState<FrictionItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [filterEnergy, setFilterEnergy] = useState<EnergyLevel | 'all'>('all');
  const [showNewTaskModal, setShowNewTaskModal] = useState(false);
  const [decomposing, setDecomposing] = useState<string | null>(null);
  const [subtasks, setSubtasks] = useState<{ [key: string]: Subtask[] }>({});
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Load tasks
  const loadTasks = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const res = await api.getTasks({});
      if (res.success && res.data) {
        // Map API response to Task interface
        const taskList = res.data.tasks.map((t: any) => ({
          id: t.id,
          title: t.request || t.title,
          description: t.description,
          status: t.status === 'running' ? 'in_progress' : t.status,
          energyRequired: ('medium' as EnergyLevel), // Would come from API
          estimatedTime: t.estimated_time,
          category: t.channel,
          createdAt: new Date(t.created_at || Date.now()),
          completedAt: t.completed_at ? new Date(t.completed_at) : undefined,
        }));
        setTasks(taskList);
      } else if (isDemo) {
        setTasks(demoTasks);
      }

      // Load friction items
      const frictionRes = await api.getTaskFriction();
      if (frictionRes.success && frictionRes.data) {
        setFriction(frictionRes.data.friction_items);
      } else if (isDemo) {
        setFriction(demoFriction);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load tasks');
      if (isDemo) {
        setTasks(demoTasks);
        setFriction(demoFriction);
      }
    }

    setIsLoading(false);
  }, []);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  // Filter tasks
  const pendingTasks = tasks.filter((t) => t.status === 'pending' || t.status === 'in_progress');
  const completedTasks = tasks.filter((t) => t.status === 'completed');
  const currentTask = pendingTasks[0];
  const upNextTasks = pendingTasks.slice(1, 3);
  const remainingTasks = pendingTasks.slice(3);

  // Filter by energy
  const filterByEnergy = (taskList: Task[]) => {
    if (filterEnergy === 'all') return taskList;
    return taskList.filter((t) => t.energyRequired === filterEnergy);
  };

  const handleComplete = async (taskId: string) => {
    setActionLoading(taskId);
    try {
      const res = await api.completeTask(taskId);
      if (res.success) {
        setTasks((prev) =>
          prev.map((t) =>
            t.id === taskId
              ? { ...t, status: 'completed' as const, completedAt: new Date() }
              : t
          )
        );
      }
    } catch (e) {
      console.error('Failed to complete task:', e);
    }
    setActionLoading(null);
  };

  const handleSkip = async (taskId: string) => {
    setActionLoading(taskId);
    try {
      const res = await api.skipTask(taskId);
      if (res.success) {
        // Move to end of list
        setTasks((prev) => {
          const task = prev.find((t) => t.id === taskId);
          if (!task) return prev;
          return [...prev.filter((t) => t.id !== taskId), task];
        });
      }
    } catch (e) {
      console.error('Failed to skip task:', e);
    }
    setActionLoading(null);
  };

  const handleStuck = async (taskId: string) => {
    setActionLoading(taskId);
    try {
      const res = await api.markTaskStuck(taskId);
      if (res.success && res.data?.data) {
        // Add to friction list if not already there
        const frictionData = res.data.data as { blocker?: string; suggestions?: string[] };
        const task = tasks.find((t) => t.id === taskId);
        if (task && frictionData.blocker) {
          setFriction((prev) => {
            if (prev.some((f) => f.task_id === taskId)) return prev;
            return [
              ...prev,
              {
                task_id: taskId,
                task_title: task.title,
                blocker: frictionData.blocker || 'Unknown blocker',
                suggested_action: frictionData.suggestions?.[0],
                confidence: 0.8,
              },
            ];
          });
        }
      }
    } catch (e) {
      console.error('Failed to analyze friction:', e);
    }
    setActionLoading(null);
  };

  const handleDecompose = async (taskId: string) => {
    setDecomposing(taskId);
    try {
      const res = await api.decomposeTask(taskId);
      if (res.success && res.data?.data?.subtasks) {
        setSubtasks((prev) => ({
          ...prev,
          [taskId]: res.data?.data?.subtasks as Subtask[],
        }));
      }
    } catch (e) {
      console.error('Failed to decompose task:', e);
    }
    setDecomposing(null);
  };

  const handleResolveFriction = (item: FrictionItem) => {
    // Remove from friction list
    setFriction((prev) => prev.filter((f) => f.task_id !== item.task_id));
  };

  const handleCreateTask = async (title: string, description?: string, category?: string) => {
    try {
      const res = await api.createTask({ title, description, category });
      if (res.success && res.data) {
        // Reload tasks
        loadTasks();
        setShowNewTaskModal(false);
      }
    } catch (e) {
      console.error('Failed to create task:', e);
    }
  };

  return (
    <div className="space-y-8 pt-4 animate-fade-in">
      {/* Error banner */}
      {error && !isDemo && (
        <div className="bg-status-error/10 border border-status-error/30 rounded-2xl px-4 py-3 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-status-error flex-shrink-0" />
          <p className="text-body text-status-error">{error}</p>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <Target className="w-6 h-6 text-white/40" />
            <h1 className="text-2xl font-light tracking-wide text-white/90">Tasks</h1>
          </div>
          <p className="text-xs text-white/40 mt-1 tracking-wide">
            {pendingTasks.length} pending, {completedTasks.length} completed today
          </p>
        </div>
        <button
          onClick={() => setShowNewTaskModal(true)}
          className="btn btn-primary flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          New Task
        </button>
      </div>

      {/* Current Task - THE NOW */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <Target className="w-5 h-5 text-accent-primary" />
          <h2 className="text-section-header text-text-primary">Now</h2>
        </div>

        {isLoading ? (
          <div className="crystal-card p-8">
            <div className="flex items-center justify-center">
              <RefreshCw className="w-6 h-6 text-text-muted animate-spin" />
            </div>
          </div>
        ) : currentTask ? (
          <CurrentTaskCard
            task={currentTask}
            subtasks={subtasks[currentTask.id]}
            isDecomposing={decomposing === currentTask.id}
            isLoading={actionLoading === currentTask.id}
            onComplete={() => handleComplete(currentTask.id)}
            onSkip={() => handleSkip(currentTask.id)}
            onStuck={() => handleStuck(currentTask.id)}
            onDecompose={() => handleDecompose(currentTask.id)}
          />
        ) : (
          <div className="crystal-card p-8 text-center">
            <div className="flex flex-col items-center gap-4">
              <div className="w-16 h-16 rounded-full bg-accent-muted flex items-center justify-center">
                <Check className="w-8 h-8 text-accent-primary" />
              </div>
              <div>
                <h3 className="text-section-header text-text-primary mb-1">All done!</h3>
                <p className="text-body text-text-secondary">
                  No tasks waiting. Add something new or take a break.
                </p>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Friction Detected */}
      {friction.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="w-5 h-5 text-status-warning" />
            <h2 className="text-section-header text-text-primary">Friction Detected</h2>
          </div>
          <div className="space-y-2">
            {friction.map((item) => (
              <div
                key={item.task_id}
                className="crystal-card p-4 border-status-warning/30"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-body text-text-primary mb-2">
                      <span className="font-medium">{item.task_title}</span> needs:{' '}
                      {item.blocker}
                    </p>
                    {item.suggested_action && (
                      <button
                        onClick={() => handleResolveFriction(item)}
                        className="btn btn-secondary text-caption"
                      >
                        {item.suggested_action}
                      </button>
                    )}
                  </div>
                  <button
                    onClick={() => handleResolveFriction(item)}
                    className="p-1 text-text-muted hover:text-text-primary"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Up Next */}
      {upNextTasks.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <ChevronRight className="w-5 h-5 text-text-muted" />
              <h2 className="text-section-header text-text-primary">
                Up Next ({upNextTasks.length})
              </h2>
            </div>
            {remainingTasks.length > 0 && (
              <button className="btn btn-ghost text-caption">
                Show all ({pendingTasks.length})
              </button>
            )}
          </div>
          <div className="space-y-2">
            {upNextTasks.map((task) => (
              <TaskRow
                key={task.id}
                task={task}
                isLoading={actionLoading === task.id}
                onComplete={() => handleComplete(task.id)}
              />
            ))}
          </div>
        </section>
      )}

      {/* Completed Today */}
      {completedTasks.length > 0 && (
        <section>
          <button
            onClick={() => setShowCompleted(!showCompleted)}
            className="flex items-center gap-2 text-text-secondary hover:text-text-primary transition-colors mb-4"
          >
            <ChevronDown
              className={cn(
                'w-5 h-5 transition-transform',
                showCompleted && 'rotate-180'
              )}
            />
            <h2 className="text-section-header">
              Completed Today ({completedTasks.length})
            </h2>
          </button>
          {showCompleted && (
            <div className="space-y-2 animate-fade-in">
              {completedTasks.map((task) => (
                <TaskRow key={task.id} task={task} completed />
              ))}
            </div>
          )}
        </section>
      )}

      {/* New Task Modal */}
      {showNewTaskModal && (
        <NewTaskModal
          onClose={() => setShowNewTaskModal(false)}
          onCreate={handleCreateTask}
        />
      )}
    </div>
  );
}

// Current task card - prominent display
function CurrentTaskCard({
  task,
  subtasks,
  isDecomposing,
  isLoading,
  onComplete,
  onSkip,
  onStuck,
  onDecompose,
}: {
  task: Task;
  subtasks?: Subtask[];
  isDecomposing: boolean;
  isLoading: boolean;
  onComplete: () => void;
  onSkip: () => void;
  onStuck: () => void;
  onDecompose: () => void;
}) {
  return (
    <div className="crystal-card p-6 md:p-8">
      {/* Main Content */}
      <h3 className="text-step-title text-text-primary mb-4 leading-relaxed">
        {task.title}
      </h3>

      {task.description && (
        <p className="text-body-lg text-text-secondary mb-6">
          {task.description}
        </p>
      )}

      {/* Meta info */}
      <div className="flex flex-wrap items-center gap-4 mb-8 text-caption">
        <EnergyIndicator level={task.energyRequired} showLabel />
        {task.estimatedTime && (
          <span className="flex items-center gap-1.5 text-text-muted">
            <Clock className="w-3.5 h-3.5" />
            <span>~{task.estimatedTime}</span>
          </span>
        )}
        {task.category && (
          <span className="flex items-center gap-1.5 text-text-muted">
            <Tag className="w-3.5 h-3.5" />
            <span>{task.category}</span>
          </span>
        )}
      </div>

      {/* Subtasks (if decomposed) */}
      {subtasks && subtasks.length > 0 && (
        <div className="mb-6 p-4 bg-bg-surface rounded-xl">
          <p className="text-caption text-text-muted mb-3">Broken down into:</p>
          <ol className="space-y-2 list-decimal list-inside">
            {subtasks.map((st, idx) => (
              <li key={idx} className="text-body text-text-primary">
                {st.title}
                {st.energy && (
                  <span className="ml-2 text-caption text-text-muted">
                    ({st.energy} energy)
                  </span>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-3">
        <button
          onClick={onComplete}
          disabled={isLoading}
          className="btn-action flex items-center gap-2"
        >
          {isLoading ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <Check className="w-5 h-5" />
          )}
          Done
        </button>
        <button
          onClick={onSkip}
          disabled={isLoading}
          className="btn btn-ghost flex items-center gap-2"
        >
          <SkipForward className="w-4 h-4" />
          Skip for now
        </button>
        <button
          onClick={onStuck}
          disabled={isLoading}
          className="btn btn-ghost flex items-center gap-2"
        >
          <HelpCircle className="w-4 h-4" />
          I&apos;m stuck
        </button>
        <button
          onClick={onDecompose}
          disabled={isDecomposing || isLoading}
          className="btn btn-ghost flex items-center gap-2"
        >
          {isDecomposing ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <ListTree className="w-4 h-4" />
          )}
          Break down
        </button>
      </div>
    </div>
  );
}

// Task row for up next / completed lists
function TaskRow({
  task,
  completed = false,
  isLoading = false,
  onComplete,
}: {
  task: Task;
  completed?: boolean;
  isLoading?: boolean;
  onComplete?: () => void;
}) {
  return (
    <div
      className={cn(
        'crystal-card p-4 flex items-center gap-4',
        completed && 'opacity-60'
      )}
    >
      {/* Checkbox */}
      <button
        onClick={onComplete}
        disabled={completed || isLoading}
        className={cn(
          'w-6 h-6 rounded-lg border-2 flex items-center justify-center transition-colors flex-shrink-0',
          completed
            ? 'bg-accent-primary border-accent-primary'
            : 'border-border-default hover:border-accent-primary'
        )}
      >
        {isLoading ? (
          <Loader2 className="w-4 h-4 text-text-muted animate-spin" />
        ) : completed ? (
          <Check className="w-4 h-4 text-white" />
        ) : null}
      </button>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p
          className={cn(
            'text-body truncate',
            completed ? 'text-text-muted line-through' : 'text-text-primary'
          )}
        >
          {task.title}
        </p>
        <div className="flex items-center gap-3 mt-1">
          <EnergyIndicator level={task.energyRequired} showLabel={false} />
          {task.estimatedTime && (
            <span className="text-caption text-text-muted">~{task.estimatedTime}</span>
          )}
          {task.category && (
            <span className="text-caption text-text-muted">{task.category}</span>
          )}
        </div>
      </div>
    </div>
  );
}

// New Task Modal
function NewTaskModal({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (title: string, description?: string, category?: string) => void;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    setIsCreating(true);
    await onCreate(title, description || undefined, category || undefined);
    setIsCreating(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative crystal-card p-6 w-full max-w-md">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-section-header text-text-primary">New Task</h2>
          <button onClick={onClose} className="p-1 text-text-muted hover:text-text-primary">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-caption text-text-muted mb-1">
              What needs to be done?
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Enter task..."
              className="w-full px-4 py-2 bg-bg-surface rounded-lg text-body text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-primary/30"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-caption text-text-muted mb-1">
              Details (optional)
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Add more context..."
              rows={3}
              className="w-full px-4 py-2 bg-bg-surface rounded-lg text-body text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-primary/30 resize-none"
            />
          </div>

          <div>
            <label className="block text-caption text-text-muted mb-1">
              Category (optional)
            </label>
            <input
              type="text"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="e.g., Work, Personal, Admin"
              className="w-full px-4 py-2 bg-bg-surface rounded-lg text-body text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-primary/30"
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 btn btn-ghost"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!title.trim() || isCreating}
              className="flex-1 btn btn-primary flex items-center justify-center gap-2"
            >
              {isCreating ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Plus className="w-4 h-4" />
              )}
              Add Task
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
