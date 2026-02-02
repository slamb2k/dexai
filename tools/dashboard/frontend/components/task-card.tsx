'use client';

import { cn, formatDuration, formatCurrency, formatTimestamp } from '@/lib/utils';
import {
  CheckCircle2,
  Circle,
  XCircle,
  Loader2,
  Clock,
  ChevronRight,
} from 'lucide-react';

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface Task {
  id: string;
  status: TaskStatus;
  request: string;
  channel?: string;
  startTime?: Date | string;
  endTime?: Date | string;
  duration?: number; // seconds
  cost?: number;
  toolsUsed?: string[];
}

interface TaskCardProps {
  task: Task;
  onClick?: () => void;
  compact?: boolean;
  className?: string;
}

const statusConfig: Record<
  TaskStatus,
  { icon: typeof CheckCircle2; color: string; bgColor: string; label: string }
> = {
  pending: {
    icon: Circle,
    color: 'text-text-muted',
    bgColor: 'bg-text-muted/10',
    label: 'Pending',
  },
  running: {
    icon: Loader2,
    color: 'text-accent-primary',
    bgColor: 'bg-accent-primary/10',
    label: 'Running',
  },
  completed: {
    icon: CheckCircle2,
    color: 'text-status-success',
    bgColor: 'bg-status-success/10',
    label: 'Completed',
  },
  failed: {
    icon: XCircle,
    color: 'text-status-error',
    bgColor: 'bg-status-error/10',
    label: 'Failed',
  },
};

export function TaskCard({ task, onClick, compact = false, className }: TaskCardProps) {
  const config = statusConfig[task.status];
  const Icon = config.icon;

  if (compact) {
    return (
      <button
        onClick={onClick}
        className={cn(
          'w-full flex items-center gap-3 px-3 py-2 rounded-button text-left transition-colors',
          'hover:bg-bg-elevated',
          className
        )}
      >
        <Icon
          size={16}
          className={cn(config.color, task.status === 'running' && 'animate-spin')}
        />
        <span className="text-body text-text-secondary flex-1 truncate">
          {task.request}
        </span>
        {task.channel && (
          <span className="text-caption text-text-muted">{task.channel}</span>
        )}
        <ChevronRight size={16} className="text-text-muted" />
      </button>
    );
  }

  return (
    <button
      onClick={onClick}
      className={cn(
        'card w-full p-4 text-left transition-all hover:shadow-glow-blue',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <span
          className={cn(
            'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-caption font-medium',
            config.bgColor,
            config.color
          )}
        >
          <Icon
            size={14}
            className={task.status === 'running' ? 'animate-spin' : ''}
          />
          {config.label}
        </span>

        {/* Time range */}
        {task.startTime && (
          <span className="text-caption text-text-muted font-mono">
            {formatTimestamp(task.startTime)}
            {task.endTime && ` - ${formatTimestamp(task.endTime)}`}
          </span>
        )}
      </div>

      {/* Request text */}
      <p className="text-body text-text-primary mb-4 line-clamp-2">
        &quot;{task.request}&quot;
      </p>

      {/* Footer meta */}
      <div className="flex items-center justify-between text-caption text-text-muted">
        <div className="flex items-center gap-4">
          {task.channel && (
            <span className="flex items-center gap-1">
              Channel: <span className="text-text-secondary">{task.channel}</span>
            </span>
          )}

          {task.duration !== undefined && (
            <span className="flex items-center gap-1">
              <Clock size={12} />
              {formatDuration(task.duration)}
            </span>
          )}

          {task.cost !== undefined && (
            <span className="text-text-secondary">
              {formatCurrency(task.cost)}
            </span>
          )}
        </div>

        <span className="flex items-center gap-1 text-accent-primary">
          Details
          <ChevronRight size={14} />
        </span>
      </div>
    </button>
  );
}

// Task list component
interface TaskListProps {
  tasks: Task[];
  onTaskClick?: (task: Task) => void;
  emptyMessage?: string;
  className?: string;
}

export function TaskList({
  tasks,
  onTaskClick,
  emptyMessage = 'No tasks found',
  className,
}: TaskListProps) {
  if (tasks.length === 0) {
    return (
      <div className={cn('text-center py-8', className)}>
        <p className="text-body text-text-muted">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className={cn('space-y-3', className)}>
      {tasks.map((task) => (
        <TaskCard
          key={task.id}
          task={task}
          onClick={onTaskClick ? () => onTaskClick(task) : undefined}
        />
      ))}
    </div>
  );
}
