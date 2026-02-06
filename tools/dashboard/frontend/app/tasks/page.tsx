'use client';

import { useEffect, useState } from 'react';
import { TaskCard, TaskList, Task, TaskStatus } from '@/components/task-card';
import { useTasksStore } from '@/lib/store';
import { api } from '@/lib/api';
import { cn, formatDuration, formatCurrency, formatTimestamp, formatDate } from '@/lib/utils';
import {
  Filter,
  RefreshCw,
  X,
  Clock,
  DollarSign,
  MessageSquare,
  Wrench,
  ChevronDown,
  AlertCircle,
  Inbox,
} from 'lucide-react';

const isDemo = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

// Demo mode fallback data
const demoTasks: Task[] = [
  {
    id: '1',
    status: 'completed',
    request: 'Schedule dentist appointment for next week',
    channel: 'Telegram',
    startTime: new Date(Date.now() - 30 * 60 * 1000),
    endTime: new Date(Date.now() - 27 * 60 * 1000),
    duration: 192,
    cost: 0.04,
    toolsUsed: ['calendar_create', 'send_message'],
  },
  {
    id: '2',
    status: 'completed',
    request: 'Summarize the meeting notes from yesterday',
    channel: 'Discord',
    startTime: new Date(Date.now() - 2 * 60 * 60 * 1000),
    endTime: new Date(Date.now() - 2 * 60 * 60 * 1000 + 45000),
    duration: 45,
    cost: 0.02,
    toolsUsed: ['memory_search', 'summarize'],
  },
  {
    id: '3',
    status: 'running',
    request: 'Research best practices for time blocking',
    channel: 'Web',
    startTime: new Date(Date.now() - 2 * 60 * 1000),
    duration: 120,
    cost: 0.01,
    toolsUsed: ['web_search'],
  },
  {
    id: '4',
    status: 'failed',
    request: 'Send email to John about project status',
    channel: 'Email',
    startTime: new Date(Date.now() - 4 * 60 * 60 * 1000),
    endTime: new Date(Date.now() - 4 * 60 * 60 * 1000 + 10000),
    duration: 10,
    cost: 0.01,
  },
  {
    id: '5',
    status: 'pending',
    request: 'Remind me to call mom at 5pm',
    channel: 'Telegram',
  },
];

const statusOptions: { value: TaskStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All Status' },
  { value: 'pending', label: 'Pending' },
  { value: 'running', label: 'Running' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
];

const channelOptions = [
  { value: 'all', label: 'All Channels' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'discord', label: 'Discord' },
  { value: 'slack', label: 'Slack' },
  { value: 'email', label: 'Email' },
  { value: 'web', label: 'Web' },
];

export default function TasksPage() {
  const { tasks, setTasks, selectedTask, setSelectedTask, filters, setFilters } =
    useTasksStore();
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isEmpty, setIsEmpty] = useState(false);
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all');
  const [channelFilter, setChannelFilter] = useState('all');

  // Load tasks
  useEffect(() => {
    const loadTasks = async () => {
      setIsLoading(true);
      setError(null);
      setIsEmpty(false);

      try {
        const res = await api.getTasks({
          status: statusFilter !== 'all' ? statusFilter : undefined,
          channel: channelFilter !== 'all' ? channelFilter : undefined,
        });

        if (res.success && res.data) {
          // Map backend field names to frontend Task interface
          const taskList = res.data.tasks.map((t) => {
            // Backend returns created_at/completed_at, frontend expects startTime/endTime
            const apiTask = t as unknown as {
              id: string;
              request: string;
              status: string;
              channel?: string;
              created_at?: string;
              completed_at?: string;
              duration_seconds?: number;
              cost_usd?: number;
            };
            // Capitalize channel name for display
            const channelDisplay = apiTask.channel
              ? apiTask.channel.charAt(0).toUpperCase() + apiTask.channel.slice(1)
              : undefined;
            return {
              id: apiTask.id,
              request: apiTask.request,
              status: apiTask.status as Task['status'],
              channel: channelDisplay,
              startTime: apiTask.created_at ? new Date(apiTask.created_at) : undefined,
              endTime: apiTask.completed_at ? new Date(apiTask.completed_at) : undefined,
              duration: apiTask.duration_seconds,
              cost: apiTask.cost_usd,
            };
          });
          setTasks(taskList);
          setIsEmpty(taskList.length === 0);
        } else if (res.error) {
          throw new Error(res.error);
        }
      } catch (e) {
        const errorMsg = e instanceof Error ? e.message : 'Failed to load tasks';
        setError(errorMsg);
        // Only use demo data if explicitly in demo mode
        if (isDemo) {
          setTasks(demoTasks);
        }
      }

      setIsLoading(false);
    };

    loadTasks();
  }, [setTasks, statusFilter, channelFilter]);

  // Filter tasks
  const filteredTasks = tasks.filter((task) => {
    if (statusFilter !== 'all' && task.status !== statusFilter) return false;
    // Case-insensitive channel comparison (filter is lowercase, display is capitalized)
    if (channelFilter !== 'all' && task.channel?.toLowerCase() !== channelFilter) return false;
    return true;
  });

  const displayTasks = filteredTasks.length > 0 ? filteredTasks : (isDemo ? demoTasks : []);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Error banner */}
      {error && !isDemo && (
        <div className="bg-status-error/10 border border-status-error/30 rounded-card px-4 py-3 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-status-error flex-shrink-0" />
          <p className="text-body text-status-error">{error}</p>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-page-title text-text-primary">Tasks</h1>
        <button className="btn btn-ghost flex items-center gap-2">
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-text-muted">
          <Filter size={16} />
          <span className="text-caption">Filters:</span>
        </div>

        {/* Status filter */}
        <div className="relative">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as TaskStatus | 'all')}
            className="input pr-8 appearance-none cursor-pointer"
          >
            {statusOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <ChevronDown
            size={16}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
          />
        </div>

        {/* Channel filter */}
        <div className="relative">
          <select
            value={channelFilter}
            onChange={(e) => setChannelFilter(e.target.value)}
            className="input pr-8 appearance-none cursor-pointer"
          >
            {channelOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <ChevronDown
            size={16}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
          />
        </div>

        {/* Clear filters */}
        {(statusFilter !== 'all' || channelFilter !== 'all') && (
          <button
            onClick={() => {
              setStatusFilter('all');
              setChannelFilter('all');
            }}
            className="btn btn-ghost text-caption"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Task count */}
      <p className="text-caption text-text-muted">
        Showing {displayTasks.length} task{displayTasks.length !== 1 ? 's' : ''}
      </p>

      {/* Task list */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {isLoading ? (
          <div className="col-span-full flex items-center justify-center py-12">
            <RefreshCw size={24} className="animate-spin text-text-muted" />
          </div>
        ) : displayTasks.length === 0 ? (
          <div className="col-span-full flex flex-col items-center justify-center py-12 text-text-muted">
            <Inbox size={48} className="mb-4 opacity-50" />
            <p className="text-body">No tasks found</p>
            <p className="text-caption">Tasks will appear here when you start using DexAI</p>
          </div>
        ) : (
          displayTasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              onClick={() => setSelectedTask(task)}
            />
          ))
        )}
      </div>

      {/* Task detail modal */}
      {selectedTask && (
        <TaskDetailModal
          task={selectedTask}
          onClose={() => setSelectedTask(null)}
        />
      )}
    </div>
  );
}

// Task detail modal component
function TaskDetailModal({
  task,
  onClose,
}: {
  task: Task;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-bg-surface border border-border-default rounded-card shadow-card w-full max-w-2xl max-h-[80vh] overflow-y-auto animate-scale-in">
        {/* Header */}
        <div className="sticky top-0 bg-bg-surface border-b border-border-default px-6 py-4 flex items-center justify-between">
          <h2 className="text-section-header text-text-primary">Task Details</h2>
          <button
            onClick={onClose}
            className="p-2 rounded-button hover:bg-bg-elevated transition-colors"
          >
            <X size={20} className="text-text-muted" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Request */}
          <div>
            <h3 className="text-caption text-text-muted uppercase tracking-wider mb-2">
              Request
            </h3>
            <p className="text-body text-text-primary">&quot;{task.request}&quot;</p>
          </div>

          {/* Meta grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Status */}
            <div>
              <h3 className="text-caption text-text-muted uppercase tracking-wider mb-1">
                Status
              </h3>
              <span
                className={cn(
                  'badge',
                  task.status === 'completed' && 'badge-success',
                  task.status === 'running' && 'badge-info',
                  task.status === 'failed' && 'badge-error',
                  task.status === 'pending' && 'bg-text-muted/20 text-text-muted'
                )}
              >
                {task.status.charAt(0).toUpperCase() + task.status.slice(1)}
              </span>
            </div>

            {/* Channel */}
            <div>
              <h3 className="text-caption text-text-muted uppercase tracking-wider mb-1">
                Channel
              </h3>
              <div className="flex items-center gap-1.5 text-body text-text-secondary">
                <MessageSquare size={14} />
                {task.channel || 'N/A'}
              </div>
            </div>

            {/* Duration */}
            <div>
              <h3 className="text-caption text-text-muted uppercase tracking-wider mb-1">
                Duration
              </h3>
              <div className="flex items-center gap-1.5 text-body text-text-secondary">
                <Clock size={14} />
                {task.duration ? formatDuration(task.duration) : 'N/A'}
              </div>
            </div>

            {/* Cost */}
            <div>
              <h3 className="text-caption text-text-muted uppercase tracking-wider mb-1">
                Cost
              </h3>
              <div className="flex items-center gap-1.5 text-body text-text-secondary">
                <DollarSign size={14} />
                {task.cost !== undefined ? formatCurrency(task.cost) : 'N/A'}
              </div>
            </div>
          </div>

          {/* Time */}
          {task.startTime && (
            <div>
              <h3 className="text-caption text-text-muted uppercase tracking-wider mb-2">
                Time
              </h3>
              <p className="text-body text-text-secondary font-mono">
                {formatDate(task.startTime)} {formatTimestamp(task.startTime)}
                {task.endTime && ` - ${formatTimestamp(task.endTime)}`}
              </p>
            </div>
          )}

          {/* Tools used */}
          {task.toolsUsed && task.toolsUsed.length > 0 && (
            <div>
              <h3 className="text-caption text-text-muted uppercase tracking-wider mb-2">
                Tools Used
              </h3>
              <div className="flex flex-wrap gap-2">
                {task.toolsUsed.map((tool) => (
                  <span
                    key={tool}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-bg-elevated rounded text-caption text-text-secondary"
                  >
                    <Wrench size={12} />
                    {tool}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-border-default px-6 py-4">
          <button onClick={onClose} className="btn btn-secondary">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
