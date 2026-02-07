'use client';

import { useEffect, useState } from 'react';
import {
  Target,
  Check,
  SkipForward,
  HelpCircle,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Inbox,
  RefreshCw,
  Plus,
  Zap,
  Clock,
  Tag,
  Filter,
  AlertCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { EnergyIndicator, EnergyLevel } from '@/components/energy-selector';
import { api } from '@/lib/api';

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

interface FrictionItem {
  taskId: string;
  taskTitle: string;
  blocker: string;
  suggestedAction?: string;
}

const isDemo = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

// Demo data
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
    taskId: '3',
    taskTitle: 'Call Mike',
    blocker: 'Mike\'s phone number needed',
    suggestedAction: 'Search in contacts',
  },
];

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [friction, setFriction] = useState<FrictionItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [filterEnergy, setFilterEnergy] = useState<EnergyLevel | 'all'>('all');

  // Load tasks
  useEffect(() => {
    const loadTasks = async () => {
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
            energyRequired: 'medium' as EnergyLevel, // Default, would come from API
            estimatedTime: t.estimated_time,
            category: t.channel,
            createdAt: new Date(t.created_at || Date.now()),
            completedAt: t.completed_at ? new Date(t.completed_at) : undefined,
          }));
          setTasks(taskList);
        } else if (isDemo) {
          setTasks(demoTasks);
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
    };

    loadTasks();
  }, []);

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

  const handleComplete = (taskId: string) => {
    setTasks((prev) =>
      prev.map((t) =>
        t.id === taskId
          ? { ...t, status: 'completed' as const, completedAt: new Date() }
          : t
      )
    );
  };

  const handleSkip = (taskId: string) => {
    setTasks((prev) => {
      const task = prev.find((t) => t.id === taskId);
      if (!task) return prev;
      // Move to end of list
      return [...prev.filter((t) => t.id !== taskId), task];
    });
  };

  const handleStuck = (taskId: string) => {
    // Trigger friction detection
  };

  const handleResolveFriction = (item: FrictionItem) => {
    // Handle friction resolution
  };

  return (
    <div className="space-y-8 animate-fade-in max-w-4xl mx-auto">
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
          <h1 className="text-page-title text-text-primary">Tasks</h1>
          <p className="text-body text-text-secondary mt-1">
            {pendingTasks.length} pending, {completedTasks.length} completed today
          </p>
        </div>
        <button className="btn btn-primary flex items-center gap-2">
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
            onComplete={() => handleComplete(currentTask.id)}
            onSkip={() => handleSkip(currentTask.id)}
            onStuck={() => handleStuck(currentTask.id)}
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
                key={item.taskId}
                className="crystal-card p-4 border-status-warning/30"
              >
                <p className="text-body text-text-primary mb-2">
                  <span className="font-medium">{item.taskTitle}</span> needs:{' '}
                  {item.blocker}
                </p>
                {item.suggestedAction && (
                  <button
                    onClick={() => handleResolveFriction(item)}
                    className="btn btn-secondary text-caption"
                  >
                    {item.suggestedAction}
                  </button>
                )}
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
    </div>
  );
}

// Current task card - prominent display
function CurrentTaskCard({
  task,
  onComplete,
  onSkip,
  onStuck,
}: {
  task: Task;
  onComplete: () => void;
  onSkip: () => void;
  onStuck: () => void;
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

      {/* Actions */}
      <div className="flex flex-wrap gap-3">
        <button onClick={onComplete} className="btn-action flex items-center gap-2">
          <Check className="w-5 h-5" />
          Done
        </button>
        <button onClick={onSkip} className="btn btn-ghost flex items-center gap-2">
          <SkipForward className="w-4 h-4" />
          Skip for now
        </button>
        <button onClick={onStuck} className="btn btn-ghost flex items-center gap-2">
          <HelpCircle className="w-4 h-4" />
          I&apos;m stuck
        </button>
      </div>
    </div>
  );
}

// Task row for up next / completed lists
function TaskRow({
  task,
  completed = false,
  onComplete,
}: {
  task: Task;
  completed?: boolean;
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
        disabled={completed}
        className={cn(
          'w-6 h-6 rounded-lg border-2 flex items-center justify-center transition-colors flex-shrink-0',
          completed
            ? 'bg-accent-primary border-accent-primary'
            : 'border-border-default hover:border-accent-primary'
        )}
      >
        {completed && <Check className="w-4 h-4 text-white" />}
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
