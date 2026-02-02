'use client';

import { useEffect, useState } from 'react';
import { DexAvatar, AvatarState } from '@/components/dex-avatar';
import { StatCard } from '@/components/stat-card';
import { CompactActivityFeed, ActivityItem } from '@/components/activity-feed';
import { ListTodo, MessageSquare, DollarSign, RefreshCw } from 'lucide-react';
import { cn, formatCurrency } from '@/lib/utils';
import { useDexStore, useActivityStore, useMetricsStore } from '@/lib/store';
import { api } from '@/lib/api';
import { socketClient } from '@/lib/socket';

// Mock data for demo (will be replaced by real API calls)
const mockActivity: ActivityItem[] = [
  {
    id: '1',
    type: 'message',
    timestamp: new Date(Date.now() - 5 * 60 * 1000),
    summary: 'Responded to Telegram message',
    channel: 'Telegram',
  },
  {
    id: '2',
    type: 'task',
    timestamp: new Date(Date.now() - 10 * 60 * 1000),
    summary: 'Completed task: "Send reminder"',
    channel: 'System',
  },
  {
    id: '3',
    type: 'system',
    timestamp: new Date(Date.now() - 15 * 60 * 1000),
    summary: 'Context snapshot saved',
  },
  {
    id: '4',
    type: 'llm',
    timestamp: new Date(Date.now() - 20 * 60 * 1000),
    summary: 'Claude API response received (342 tokens)',
  },
  {
    id: '5',
    type: 'message',
    timestamp: new Date(Date.now() - 30 * 60 * 1000),
    summary: 'Received message from @user',
    channel: 'Discord',
  },
];

export default function HomePage() {
  const { avatarState, currentTask, setAvatarState, setCurrentTask } = useDexStore();
  const { items: activityItems, setItems, addItem, isConnected, setConnected } = useActivityStore();
  const { tasksToday, messagesToday, costToday, updateMetrics } = useMetricsStore();

  const [isLoading, setIsLoading] = useState(true);

  // Load initial data
  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);

      try {
        // Try to fetch real data
        const [statusRes, metricsRes, activityRes] = await Promise.all([
          api.getStatus(),
          api.getMetricsSummary(),
          api.getActivity({ limit: 10 }),
        ]);

        if (statusRes.success && statusRes.data) {
          setAvatarState(statusRes.data.state as AvatarState);
          setCurrentTask(statusRes.data.currentTask || null);
        }

        if (metricsRes.success && metricsRes.data) {
          updateMetrics({
            tasksToday: metricsRes.data.tasksToday,
            messagesToday: metricsRes.data.messagesToday,
            costToday: metricsRes.data.costToday,
          });
        }

        if (activityRes.success && activityRes.data) {
          setItems(
            activityRes.data.events.map((e) => ({
              ...e,
              timestamp: new Date(e.timestamp),
            }))
          );
        }
      } catch {
        // Use mock data if API is unavailable
        setItems(mockActivity);
        updateMetrics({
          tasksToday: 12,
          messagesToday: 47,
          costToday: 0.23,
        });
      }

      setIsLoading(false);
    };

    loadData();
  }, [setAvatarState, setCurrentTask, setItems, updateMetrics]);

  // Set up WebSocket connection
  useEffect(() => {
    socketClient.connect();

    const unsubConnect = socketClient.onConnect(() => {
      setConnected(true);
    });

    const unsubDisconnect = socketClient.onDisconnect(() => {
      setConnected(false);
    });

    const unsubState = socketClient.onDexState((event) => {
      setAvatarState(event.state as AvatarState);
      setCurrentTask(event.task || null);
    });

    const unsubActivity = socketClient.onActivityNew((event) => {
      addItem({
        ...event,
        timestamp: new Date(event.timestamp),
      });
    });

    const unsubMetrics = socketClient.onMetricsUpdate((event) => {
      updateMetrics({
        tasksToday: event.tasksToday,
        messagesToday: event.messagesToday,
        costToday: event.costToday,
      });
    });

    return () => {
      unsubConnect();
      unsubDisconnect();
      unsubState();
      unsubActivity();
      unsubMetrics();
      socketClient.disconnect();
    };
  }, [setAvatarState, setCurrentTask, addItem, setConnected, updateMetrics]);

  // Demo: cycle through avatar states
  useEffect(() => {
    const states: AvatarState[] = ['idle', 'listening', 'thinking', 'working', 'success'];
    let index = 0;

    const interval = setInterval(() => {
      index = (index + 1) % states.length;
      setAvatarState(states[index]);
    }, 5000);

    return () => clearInterval(interval);
  }, [setAvatarState]);

  const displayActivity = activityItems.length > 0 ? activityItems : mockActivity;

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Connection status */}
      <div className="flex items-center justify-end gap-2">
        <span
          className={cn(
            'w-2 h-2 rounded-full',
            isConnected ? 'bg-status-success' : 'bg-status-error'
          )}
        />
        <span className="text-caption text-text-muted">
          {isConnected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      {/* Main avatar section */}
      <section className="flex flex-col items-center py-8">
        <DexAvatar
          state={avatarState}
          size="xl"
          showLabel
          currentTask={currentTask || undefined}
        />
      </section>

      {/* Quick stats */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard
          label="Tasks Today"
          value={isLoading ? '...' : tasksToday}
          icon={ListTodo}
          trend={{ value: 12, direction: 'up' }}
          sparklineData={[5, 8, 12, 10, 15, 12, 18]}
        />
        <StatCard
          label="Messages Today"
          value={isLoading ? '...' : messagesToday}
          icon={MessageSquare}
          trend={{ value: 5, direction: 'up' }}
          sparklineData={[20, 25, 30, 28, 35, 40, 47]}
        />
        <StatCard
          label="Cost Today"
          value={isLoading ? '...' : formatCurrency(costToday)}
          icon={DollarSign}
          trend={{ value: 3, direction: 'down' }}
          sparklineData={[0.15, 0.18, 0.22, 0.20, 0.25, 0.23]}
        />
      </section>

      {/* Recent activity */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-section-header text-text-primary">Recent Activity</h2>
          <button className="btn btn-ghost flex items-center gap-2 text-caption">
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
        <div className="card p-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw size={24} className="animate-spin text-text-muted" />
            </div>
          ) : (
            <CompactActivityFeed items={displayActivity} maxItems={5} />
          )}
        </div>
      </section>

      {/* Quick actions (disabled for v1) */}
      <section>
        <h2 className="text-section-header text-text-primary mb-4">Quick Actions</h2>
        <div className="flex gap-3">
          <button className="btn btn-secondary opacity-50 cursor-not-allowed" disabled>
            New Task
          </button>
          <button className="btn btn-secondary opacity-50 cursor-not-allowed" disabled>
            Quick Note
          </button>
        </div>
        <p className="text-caption text-text-muted mt-2">
          Quick actions coming in a future update
        </p>
      </section>
    </div>
  );
}
