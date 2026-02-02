'use client';

import { useEffect, useState } from 'react';
import { StatCard, AccentStatCard } from '@/components/stat-card';
import { api } from '@/lib/api';
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
} from 'lucide-react';

// Mock data
const mockDailyCost = [
  { date: 'Mon', value: 0.15 },
  { date: 'Tue', value: 0.22 },
  { date: 'Wed', value: 0.18 },
  { date: 'Thu', value: 0.31 },
  { date: 'Fri', value: 0.27 },
  { date: 'Sat', value: 0.12 },
  { date: 'Sun', value: 0.23 },
];

const mockMessagesByChannel = [
  { channel: 'Telegram', count: 45 },
  { channel: 'Discord', count: 32 },
  { channel: 'Email', count: 18 },
  { channel: 'Web', count: 12 },
];

const mockCostBreakdown = [
  { name: 'Claude API', value: 1.23, color: '#3b82f6' },
  { name: 'Tools', value: 0.15, color: '#06b6d4' },
  { name: 'Storage', value: 0.05, color: '#10b981' },
];

const mockTaskCompletion = [
  { date: 'Mon', completed: 8, failed: 1 },
  { date: 'Tue', completed: 12, failed: 2 },
  { date: 'Wed', completed: 10, failed: 0 },
  { date: 'Thu', completed: 15, failed: 1 },
  { date: 'Fri', completed: 11, failed: 3 },
  { date: 'Sat', completed: 6, failed: 0 },
  { date: 'Sun', completed: 9, failed: 1 },
];

const timeframeOptions = [
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: '90d', label: 'Last 90 days' },
];

export default function MetricsPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [timeframe, setTimeframe] = useState('7d');
  const [metrics, setMetrics] = useState({
    tasksToday: 12,
    tasksWeek: 71,
    messagesToday: 47,
    messagesWeek: 312,
    costToday: 0.23,
    costWeek: 1.48,
    costMonth: 4.82,
    avgResponseTime: 2.3,
    taskCompletionRate: 94.2,
    errorRate: 2.8,
  });

  // Load metrics
  useEffect(() => {
    const loadMetrics = async () => {
      setIsLoading(true);

      try {
        const res = await api.getMetricsSummary();
        if (res.success && res.data) {
          setMetrics(res.data);
        }
      } catch {
        // Keep mock data
      }

      setIsLoading(false);
    };

    loadMetrics();
  }, [timeframe]);

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
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-page-title text-text-primary">Metrics</h1>
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
            value={`${metrics.avgResponseTime}s`}
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
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={mockDailyCost}>
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
          </div>
        </div>

        {/* Messages by channel */}
        <div className="card p-6">
          <h3 className="text-card-title text-text-primary mb-4">
            Messages by Channel
          </h3>
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={mockMessagesByChannel}>
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
          </div>
        </div>

        {/* Task completion */}
        <div className="card p-6">
          <h3 className="text-card-title text-text-primary mb-4">
            Task Completion
          </h3>
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={mockTaskCompletion}>
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
          </div>
        </div>

        {/* Cost breakdown pie chart */}
        <div className="card p-6">
          <h3 className="text-card-title text-text-primary mb-4">
            Cost Breakdown
          </h3>
          <div className="h-[250px] flex items-center">
            <div className="w-1/2 h-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={mockCostBreakdown}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    dataKey="value"
                    stroke="#0a0a0f"
                    strokeWidth={2}
                  >
                    {mockCostBreakdown.map((entry, index) => (
                      <Cell key={index} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="w-1/2 space-y-3">
              {mockCostBreakdown.map((item) => (
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
          </div>
        </div>
      </section>
    </div>
  );
}
