'use client';

import { useEffect, useState } from 'react';
import { DexAvatar, AvatarState } from '@/components/dex-avatar';
import { StatCard } from '@/components/stat-card';
import { CompactActivityFeed, ActivityItem } from '@/components/activity-feed';
import { ListTodo, MessageSquare, DollarSign, RefreshCw, AlertCircle } from 'lucide-react';
import { cn, formatCurrency } from '@/lib/utils';
import { useDexStore, useActivityStore, useMetricsStore } from '@/lib/store';
import { api } from '@/lib/api';
import { socketClient } from '@/lib/socket';

// Demo mode fallback data
const demoActivity: ActivityItem[] = [
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

const isDemo = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

export default function HomePage() {
  const { avatarState, currentTask, setAvatarState, setCurrentTask } = useDexStore();
  const { items: activityItems, setItems, addItem, isConnected, setConnected } = useActivityStore();
  const { tasksToday, messagesToday, costToday, updateMetrics } = useMetricsStore();

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isEmpty, setIsEmpty] = useState(false);

  // Load initial data
  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      setError(null);
      setIsEmpty(false);

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
          // Map backend field names (snake_case in quick_stats) to frontend (camelCase)
          const apiMetrics = metricsRes.data as unknown as {
            quick_stats?: {
              tasks_today?: number;
              messages_today?: number;
              cost_today_usd?: number;
            };
            tasksToday?: number;
            messagesToday?: number;
            costToday?: number;
          };
          const quickStats = apiMetrics.quick_stats;
          updateMetrics({
            tasksToday: quickStats?.tasks_today ?? apiMetrics.tasksToday ?? 0,
            messagesToday: quickStats?.messages_today ?? apiMetrics.messagesToday ?? 0,
            costToday: quickStats?.cost_today_usd ?? apiMetrics.costToday ?? 0,
          });
        }

        if (activityRes.success && activityRes.data) {
          // Map backend field names to frontend ActivityItem interface
          const events = activityRes.data.events.map((e) => {
            const apiEvent = e as unknown as {
              id: string | number;
              event_type?: string;
              type?: string;
              timestamp: string;
              summary: string;
              channel?: string;
              details?: string;
              severity?: string;
            };
            // Capitalize channel for display
            const channelDisplay = apiEvent.channel
              ? apiEvent.channel.charAt(0).toUpperCase() + apiEvent.channel.slice(1)
              : undefined;
            return {
              id: String(apiEvent.id),
              type: (apiEvent.event_type || apiEvent.type || 'system') as ActivityItem['type'],
              timestamp: new Date(apiEvent.timestamp),
              summary: apiEvent.summary,
              channel: channelDisplay,
              details: apiEvent.details,
            };
          });
          setItems(events);
          setIsEmpty(events.length === 0);
        } else if (activityRes.error) {
          throw new Error(activityRes.error);
        }
      } catch (e) {
        const errorMsg = e instanceof Error ? e.message : 'Failed to load data';
        setError(errorMsg);
        // Only use demo data if explicitly in demo mode
        if (isDemo) {
          setItems(demoActivity);
          updateMetrics({
            tasksToday: 12,
            messagesToday: 47,
            costToday: 0.23,
          });
        }
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
      // Map backend field names to frontend ActivityItem interface
      const wsEvent = event as unknown as {
        id: string | number;
        event_type?: string;
        type?: string;
        timestamp: string;
        summary: string;
        channel?: string;
        details?: string;
        severity?: string;
      };
      const channelDisplay = wsEvent.channel
        ? wsEvent.channel.charAt(0).toUpperCase() + wsEvent.channel.slice(1)
        : undefined;
      addItem({
        id: String(wsEvent.id),
        type: (wsEvent.event_type || wsEvent.type || 'system') as ActivityItem['type'],
        timestamp: new Date(wsEvent.timestamp),
        summary: wsEvent.summary,
        channel: channelDisplay,
        details: wsEvent.details,
      });
    });

    const unsubMetrics = socketClient.onMetricsUpdate((event) => {
      // Map backend field names (snake_case) to frontend (camelCase)
      const wsMetrics = event as unknown as {
        tasks_today?: number;
        messages_today?: number;
        cost_today_usd?: number;
        tasksToday?: number;
        messagesToday?: number;
        costToday?: number;
      };
      updateMetrics({
        tasksToday: wsMetrics.tasks_today ?? wsMetrics.tasksToday ?? 0,
        messagesToday: wsMetrics.messages_today ?? wsMetrics.messagesToday ?? 0,
        costToday: wsMetrics.cost_today_usd ?? wsMetrics.costToday ?? 0,
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

  const displayActivity = activityItems.length > 0 ? activityItems : (isDemo ? demoActivity : []);

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Error banner */}
      {error && !isDemo && (
        <div className="bg-status-error/10 border border-status-error/30 rounded-card px-4 py-3 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-status-error flex-shrink-0" />
          <p className="text-body text-status-error">{error}</p>
        </div>
      )}

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
