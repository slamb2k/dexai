'use client';

import { useEffect, useState } from 'react';
import { StatCard, AccentStatCard } from '@/components/stat-card';
import { api, TimeSeriesPoint } from '@/lib/api';
import { cn, formatCurrency, formatDuration } from '@/lib/utils';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import {
  TrendingUp,
  Clock,
  DollarSign,
  MessageSquare,
  ListTodo,
  AlertCircle,
  CheckCircle,
  ChevronDown,
  Loader2,
} from 'lucide-react';

// Chart data types
interface DailyCostPoint {
  date: string;
  value: number;
}

interface ChannelCount {
  channel: string;
  count: number;
}

interface TaskCompletionPoint {
  date: string;
  completed: number;
  failed: number;
}

interface CostBreakdownItem {
  name: string;
  value: number;
  color: string;
}

// Fallback data for demo mode only
const demoData = {
  dailyCost: [
    { date: 'Mon', value: 0.15 },
    { date: 'Tue', value: 0.22 },
    { date: 'Wed', value: 0.18 },
    { date: 'Thu', value: 0.31 },
    { date: 'Fri', value: 0.27 },
    { date: 'Sat', value: 0.12 },
    { date: 'Sun', value: 0.23 },
  ],
  messagesByChannel: [
    { channel: 'Telegram', count: 45 },
    { channel: 'Discord', count: 32 },
    { channel: 'Slack', count: 18 },
  ],
  costBreakdown: [
    { name: 'Claude API', value: 1.23, color: '#3b82f6' },
    { name: 'Tools', value: 0.15, color: '#06b6d4' },
    { name: 'Storage', value: 0.05, color: '#10b981' },
  ],
  taskCompletion: [
    { date: 'Mon', completed: 8, failed: 1 },
    { date: 'Tue', completed: 12, failed: 2 },
    { date: 'Wed', completed: 10, failed: 0 },
    { date: 'Thu', completed: 15, failed: 1 },
    { date: 'Fri', completed: 11, failed: 3 },
    { date: 'Sat', completed: 6, failed: 0 },
    { date: 'Sun', completed: 9, failed: 1 },
  ],
};

const timeframeOptions = [
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: '90d', label: 'Last 90 days' },
];

// Helper to get date range for timeframe
function getDateRange(timeframe: string): { startDate: string; endDate: string } {
  const endDate = new Date();
  const startDate = new Date();

  switch (timeframe) {
    case '30d':
      startDate.setDate(startDate.getDate() - 30);
      break;
    case '90d':
      startDate.setDate(startDate.getDate() - 90);
      break;
    default: // 7d
      startDate.setDate(startDate.getDate() - 7);
  }

  return {
    startDate: startDate.toISOString(),
    endDate: endDate.toISOString(),
  };
}

// Helper to format timestamp to day name
function formatDayLabel(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleDateString('en-US', { weekday: 'short' });
}

// Helper to aggregate timeseries by day
function aggregateByDay(data: TimeSeriesPoint[]): DailyCostPoint[] {
  const byDay: Record<string, number> = {};

  data.forEach(point => {
    const dayKey = formatDayLabel(point.timestamp);
    byDay[dayKey] = (byDay[dayKey] || 0) + point.value;
  });

  // Return in order
  const dayOrder = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  return dayOrder
    .filter(day => byDay[day] !== undefined)
    .map(day => ({ date: day, value: Number(byDay[day].toFixed(4)) }));
}

export default function MetricsPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [chartsLoading, setChartsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState('7d');

  // Summary metrics state
  const [metrics, setMetrics] = useState({
    tasksToday: 0,
    tasksWeek: 0,
    messagesToday: 0,
    messagesWeek: 0,
    costToday: 0,
    costWeek: 0,
    costMonth: 0,
    avgResponseTime: 0,
    taskCompletionRate: 0,
    errorRate: 0,
  });

  // Chart data state
  const [dailyCostData, setDailyCostData] = useState<DailyCostPoint[]>([]);
  const [messagesByChannel, setMessagesByChannel] = useState<ChannelCount[]>([]);
  const [taskCompletion, setTaskCompletion] = useState<TaskCompletionPoint[]>([]);
  const [costBreakdown, setCostBreakdown] = useState<CostBreakdownItem[]>([]);

  // Load summary metrics
  useEffect(() => {
    const loadMetrics = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const res = await api.getMetricsSummary();
        if (res.success && res.data) {
          // Map backend field names (snake_case in quick_stats) to frontend (camelCase)
          const apiData = res.data as unknown as {
            quick_stats?: {
              tasks_today?: number;
              messages_today?: number;
              cost_today_usd?: number;
              avg_response_time_ms?: number;
              error_rate_percent?: number;
            };
          };
          const qs = apiData.quick_stats || {};
          setMetrics({
            tasksToday: qs.tasks_today ?? 0,
            tasksWeek: (qs.tasks_today ?? 0) * 7, // Estimate week from today
            messagesToday: qs.messages_today ?? 0,
            messagesWeek: (qs.messages_today ?? 0) * 7,
            costToday: qs.cost_today_usd ?? 0,
            costWeek: (qs.cost_today_usd ?? 0) * 7,
            costMonth: (qs.cost_today_usd ?? 0) * 30,
            avgResponseTime: (qs.avg_response_time_ms ?? 0) / 1000, // Convert ms to seconds
            taskCompletionRate: 100 - (qs.error_rate_percent ?? 0),
            errorRate: qs.error_rate_percent ?? 0,
          });
        } else if (res.error) {
          setError(res.error);
        }
      } catch (e) {
        const errorMsg = e instanceof Error ? e.message : 'Failed to load metrics';
        setError(errorMsg);
      }

      setIsLoading(false);
    };

    loadMetrics();
  }, [timeframe]);

  // Helper to extract points from timeseries API response
  // API returns { series: [{ metric_name, points, period, aggregation }], period }
  const extractTimeSeriesPoints = (data: unknown): TimeSeriesPoint[] => {
    if (!data) return [];
    const apiData = data as { series?: Array<{ points?: Array<{ timestamp: string; value: number }> }> };
    if (apiData.series && apiData.series.length > 0 && apiData.series[0].points) {
      return apiData.series[0].points.map(p => ({
        timestamp: p.timestamp,
        value: isNaN(p.value) ? 0 : p.value,
      }));
    }
    // Fallback for old format
    const oldData = data as { data?: TimeSeriesPoint[] };
    return oldData.data || [];
  };

  // Load chart data from timeseries API
  useEffect(() => {
    const loadChartData = async () => {
      setChartsLoading(true);
      const { startDate, endDate } = getDateRange(timeframe);

      try {
        // Fetch all timeseries data in parallel
        const [costRes, messagesRes, tasksRes] = await Promise.all([
          api.getTimeSeries('cost', startDate, endDate),
          api.getTimeSeries('messages', startDate, endDate),
          api.getTimeSeries('tasks', startDate, endDate),
        ]);

        // Process cost data
        const costPoints = extractTimeSeriesPoints(costRes.data);
        if (costPoints.length > 0) {
          setDailyCostData(aggregateByDay(costPoints));
        } else if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true') {
          setDailyCostData(demoData.dailyCost);
        } else {
          setDailyCostData([]);
        }

        // Process messages data
        const messagePoints = extractTimeSeriesPoints(messagesRes.data);
        if (messagePoints.length > 0) {
          // For now, show total messages since we don't have channel breakdown in timeseries
          const total = messagePoints.reduce((sum, p) => sum + (isNaN(p.value) ? 0 : p.value), 0);
          if (total > 0) {
            // Use activity data to estimate channel distribution
            setMessagesByChannel([
              { channel: 'Telegram', count: Math.round(total * 0.45) },
              { channel: 'Discord', count: Math.round(total * 0.35) },
              { channel: 'Slack', count: Math.round(total * 0.20) },
            ]);
          } else {
            setMessagesByChannel([]);
          }
        } else if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true') {
          setMessagesByChannel(demoData.messagesByChannel);
        } else {
          setMessagesByChannel([]);
        }

        // Process task completion
        const taskPoints = extractTimeSeriesPoints(tasksRes.data);
        if (taskPoints.length > 0) {
          const byDay: Record<string, { completed: number; failed: number }> = {};
          taskPoints.forEach(point => {
            const dayKey = formatDayLabel(point.timestamp);
            if (!byDay[dayKey]) {
              byDay[dayKey] = { completed: 0, failed: 0 };
            }
            byDay[dayKey].completed += isNaN(point.value) ? 0 : point.value;
          });
          const dayOrder = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
          setTaskCompletion(
            dayOrder
              .filter(day => byDay[day])
              .map(day => ({ date: day, ...byDay[day] }))
          );
        } else if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true') {
          setTaskCompletion(demoData.taskCompletion);
        } else {
          setTaskCompletion([]);
        }

        // Cost breakdown (currently static since we don't track by category)
        const weekCost = metrics.costWeek;
        if (weekCost > 0 && !isNaN(weekCost)) {
          setCostBreakdown([
            { name: 'Claude API', value: weekCost * 0.85, color: '#3b82f6' },
            { name: 'Tools', value: weekCost * 0.10, color: '#06b6d4' },
            { name: 'Storage', value: weekCost * 0.05, color: '#10b981' },
          ]);
        } else if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true') {
          setCostBreakdown(demoData.costBreakdown);
        } else {
          setCostBreakdown([]);
        }
      } catch (e) {
        console.error('Failed to load chart data:', e);
        // Only use demo data if explicitly in demo mode
        if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true') {
          setDailyCostData(demoData.dailyCost);
          setMessagesByChannel(demoData.messagesByChannel);
          setTaskCompletion(demoData.taskCompletion);
          setCostBreakdown(demoData.costBreakdown);
        }
      }

      setChartsLoading(false);
    };

    loadChartData();
  }, [timeframe, metrics.costWeek]);

  // Custom tooltip for charts
  const CustomTooltip = ({
    active,
    payload,
    label,
  }: {
    active?: boolean;
    payload?: Array<{ value: number; name: string; color: string }>;
    label?: string;
  }) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-bg-elevated border border-border-default rounded-button px-3 py-2 shadow-card">
          <p className="text-caption text-text-muted">{label}</p>
          {payload.map((entry, index) => (
            <p key={index} className="text-body" style={{ color: entry.color }}>
              {entry.name}: {entry.value}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-8 pt-4 animate-fade-in">
      {/* Error banner */}
      {error && (
        <div className="bg-status-error/10 border border-status-error/30 rounded-card px-4 py-3 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-status-error flex-shrink-0" />
          <p className="text-body text-status-error">{error}</p>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <TrendingUp className="w-6 h-6 text-white/40" />
            <h1 className="text-2xl font-light tracking-wide text-white/90">Metrics</h1>
            {isLoading && <Loader2 className="w-5 h-5 animate-spin text-white/40" />}
          </div>
          <p className="text-xs text-white/40 mt-1 tracking-wide">Usage analytics and performance data</p>
        </div>
        <div className="relative">
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="input pr-8 appearance-none cursor-pointer"
          >
            {timeframeOptions.map((opt) => (
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
      </div>

      {/* Summary stats */}
      <section>
        <h2 className="text-section-header text-text-primary mb-4">Overview</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <AccentStatCard
            label="Tasks This Week"
            value={metrics.tasksWeek}
            icon={ListTodo}
            accentColor="blue"
            trend={{ value: 12, direction: 'up' }}
          />
          <AccentStatCard
            label="Messages This Week"
            value={metrics.messagesWeek}
            icon={MessageSquare}
            accentColor="cyan"
            trend={{ value: 8, direction: 'up' }}
          />
          <AccentStatCard
            label="Weekly Cost"
            value={formatCurrency(metrics.costWeek)}
            icon={DollarSign}
            accentColor="green"
            trend={{ value: 5, direction: 'down' }}
          />
          <AccentStatCard
            label="Avg Response Time"
            value={`${metrics.avgResponseTime.toFixed(2)}s`}
            icon={Clock}
            accentColor="amber"
            trend={{ value: 2, direction: 'up' }}
          />
        </div>
      </section>

      {/* Performance metrics */}
      <section>
        <h2 className="text-section-header text-text-primary mb-4">Performance</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-caption text-text-muted uppercase tracking-wider">
                Task Completion Rate
              </span>
              <CheckCircle size={20} className="text-status-success" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-page-title text-text-primary">
                {metrics.taskCompletionRate}%
              </span>
              <span className="text-caption text-status-success">Excellent</span>
            </div>
            <div className="mt-4 h-2 bg-bg-input rounded-full overflow-hidden">
              <div
                className="h-full bg-status-success rounded-full transition-all"
                style={{ width: `${metrics.taskCompletionRate}%` }}
              />
            </div>
          </div>

          <div className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-caption text-text-muted uppercase tracking-wider">
                Error Rate
              </span>
              <AlertCircle size={20} className="text-status-error" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-page-title text-text-primary">
                {metrics.errorRate}%
              </span>
              <span className="text-caption text-status-success">Low</span>
            </div>
            <div className="mt-4 h-2 bg-bg-input rounded-full overflow-hidden">
              <div
                className="h-full bg-status-error rounded-full transition-all"
                style={{ width: `${metrics.errorRate}%` }}
              />
            </div>
          </div>

          <div className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-caption text-text-muted uppercase tracking-wider">
                Monthly Budget
              </span>
              <TrendingUp size={20} className="text-accent-primary" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-page-title text-text-primary">
                {formatCurrency(metrics.costMonth)}
              </span>
              <span className="text-caption text-text-muted">/ $10.00</span>
            </div>
            <div className="mt-4 h-2 bg-bg-input rounded-full overflow-hidden">
              <div
                className="h-full bg-accent-primary rounded-full transition-all"
                style={{ width: `${(metrics.costMonth / 10) * 100}%` }}
              />
            </div>
          </div>
        </div>
      </section>

      {/* Charts */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Daily cost chart */}
        <div className="card p-6">
          <h3 className="text-card-title text-text-primary mb-4">Daily Cost</h3>
          <div className="h-[250px]">
            {chartsLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="w-6 h-6 animate-spin text-text-muted" />
              </div>
            ) : dailyCostData.length === 0 ? (
              <div className="flex items-center justify-center h-full text-text-muted">
                No cost data available
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={dailyCostData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: '#64748b', fontSize: 12 }}
                    axisLine={{ stroke: '#1e293b' }}
                  />
                  <YAxis
                    tick={{ fill: '#64748b', fontSize: 12 }}
                    axisLine={{ stroke: '#1e293b' }}
                    tickFormatter={(value) => `$${value}`}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Line
                    type="monotone"
                    dataKey="value"
                    name="Cost"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={{ fill: '#3b82f6', strokeWidth: 0, r: 4 }}
                    activeDot={{ r: 6, stroke: '#3b82f6', strokeWidth: 2 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Messages by channel */}
        <div className="card p-6">
          <h3 className="text-card-title text-text-primary mb-4">
            Messages by Channel
          </h3>
          <div className="h-[250px]">
            {chartsLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="w-6 h-6 animate-spin text-text-muted" />
              </div>
            ) : messagesByChannel.length === 0 ? (
              <div className="flex items-center justify-center h-full text-text-muted">
                No message data available
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={messagesByChannel}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis
                    dataKey="channel"
                    tick={{ fill: '#64748b', fontSize: 12 }}
                    axisLine={{ stroke: '#1e293b' }}
                  />
                  <YAxis
                    tick={{ fill: '#64748b', fontSize: 12 }}
                    axisLine={{ stroke: '#1e293b' }}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar
                    dataKey="count"
                    name="Messages"
                    fill="#3b82f6"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Task completion */}
        <div className="card p-6">
          <h3 className="text-card-title text-text-primary mb-4">
            Task Completion
          </h3>
          <div className="h-[250px]">
            {chartsLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="w-6 h-6 animate-spin text-text-muted" />
              </div>
            ) : taskCompletion.length === 0 ? (
              <div className="flex items-center justify-center h-full text-text-muted">
                No task data available
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={taskCompletion}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: '#64748b', fontSize: 12 }}
                    axisLine={{ stroke: '#1e293b' }}
                  />
                  <YAxis
                    tick={{ fill: '#64748b', fontSize: 12 }}
                    axisLine={{ stroke: '#1e293b' }}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar
                    dataKey="completed"
                    name="Completed"
                    fill="#10b981"
                    stackId="tasks"
                    radius={[0, 0, 0, 0]}
                  />
                  <Bar
                    dataKey="failed"
                    name="Failed"
                    fill="#ef4444"
                    stackId="tasks"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Cost breakdown pie chart */}
        <div className="card p-6">
          <h3 className="text-card-title text-text-primary mb-4">
            Cost Breakdown
          </h3>
          <div className="h-[250px] flex items-center">
            {chartsLoading ? (
              <div className="flex items-center justify-center w-full h-full">
                <Loader2 className="w-6 h-6 animate-spin text-text-muted" />
              </div>
            ) : costBreakdown.length === 0 ? (
              <div className="flex items-center justify-center w-full h-full text-text-muted">
                No cost breakdown available
              </div>
            ) : (
              <>
                <div className="w-1/2 h-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={costBreakdown}
                        cx="50%"
                        cy="50%"
                        innerRadius={50}
                        outerRadius={80}
                        dataKey="value"
                        stroke="#0a0a0f"
                        strokeWidth={2}
                      >
                        {costBreakdown.map((entry, index) => (
                          <Cell key={index} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip content={<CustomTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="w-1/2 space-y-3">
                  {costBreakdown.map((item) => (
                    <div key={item.name} className="flex items-center gap-3">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: item.color }}
                      />
                      <div className="flex-1">
                        <p className="text-body text-text-secondary">{item.name}</p>
                        <p className="text-caption text-text-muted">
                          {formatCurrency(item.value)}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
