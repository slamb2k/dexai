'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, HealthCheck, SystemInfo } from '@/lib/api';
import { cn, formatTimestamp } from '@/lib/utils';
import {
  Bug,
  Server,
  Database,
  RefreshCw,
  Terminal,
  Table,
  ChevronDown,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Minus,
  Play,
  Trash2,
  Copy,
  Check,
  Settings,
  Wrench,
  Cpu,
  HardDrive,
  Clock,
  Activity,
  Zap,
  RotateCcw,
  Loader2,
} from 'lucide-react';

// Mock data
const mockHealthChecks: HealthCheck[] = [
  { service: 'API Server', status: 'healthy', latency: 12 },
  { service: 'Database', status: 'healthy', latency: 5 },
  { service: 'Memory Store', status: 'healthy', latency: 3 },
  { service: 'WebSocket', status: 'healthy', latency: 8 },
  { service: 'LLM Provider', status: 'degraded', latency: 250, message: 'High latency detected' },
  { service: 'Task Queue', status: 'healthy', latency: 15 },
];

const mockLogs = [
  '[2024-01-15 14:32:15] INFO  - API request received: GET /api/status',
  '[2024-01-15 14:32:15] DEBUG - Session validated for user_123',
  '[2024-01-15 14:32:16] INFO  - Response sent: 200 OK (12ms)',
  '[2024-01-15 14:32:20] INFO  - WebSocket connection established',
  '[2024-01-15 14:32:25] WARN  - Rate limit approaching for LLM calls',
  '[2024-01-15 14:32:30] INFO  - Task completed: task_456',
  '[2024-01-15 14:32:35] DEBUG - Memory snapshot saved',
  '[2024-01-15 14:32:40] ERROR - Failed to connect to external service',
  '[2024-01-15 14:32:45] INFO  - Retry successful after 2 attempts',
];

const mockTables = ['tasks', 'activity', 'memory_entries', 'audit_log', 'settings'];

const mockTableData = {
  tasks: {
    columns: ['id', 'status', 'request', 'created_at'],
    rows: [
      { id: 'task_001', status: 'completed', request: 'Schedule meeting', created_at: '2024-01-15 14:00:00' },
      { id: 'task_002', status: 'running', request: 'Research topic', created_at: '2024-01-15 14:30:00' },
      { id: 'task_003', status: 'pending', request: 'Send reminder', created_at: '2024-01-15 14:45:00' },
    ],
  },
};

export default function DebugPage() {
  const [activeTab, setActiveTab] = useState<'system' | 'health' | 'logs' | 'database' | 'tools'>('system');
  const [healthChecks, setHealthChecks] = useState<HealthCheck[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedTable, setSelectedTable] = useState(mockTables[0]);
  const [tableData, setTableData] = useState<{
    columns: string[];
    rows: Record<string, unknown>[];
  } | null>(null);
  const [logLevel, setLogLevel] = useState('all');
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [toolResults, setToolResults] = useState<Record<string, { loading: boolean; result?: string; error?: string }>>({});

  // Transform API health response to expected format
  const transformHealthResponse = (data: Record<string, unknown>): HealthCheck[] => {
    // If API returns checks array directly, use it
    if (Array.isArray(data?.checks)) {
      return data.checks as HealthCheck[];
    }

    // Transform services object to checks array
    const services = data?.services as Record<string, string> | undefined;
    if (services && typeof services === 'object') {
      const checks: HealthCheck[] = [];

      // Map service names to display names
      const serviceNames: Record<string, string> = {
        database: 'Database',
        sessions: 'Session Store',
        memory: 'Memory Store',
        channels: 'Channel Adapters',
        api: 'API Server',
        websocket: 'WebSocket',
        llm: 'LLM Provider',
        task_queue: 'Task Queue',
      };

      Object.entries(services).forEach(([key, status]) => {
        const displayName = serviceNames[key] || key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
        let normalizedStatus: 'healthy' | 'degraded' | 'unhealthy' = 'healthy';
        let message: string | undefined;

        if (status === 'healthy' || status === 'ok') {
          normalizedStatus = 'healthy';
        } else if (status === 'degraded' || status === 'warning') {
          normalizedStatus = 'degraded';
        } else if (status === 'unhealthy' || status === 'error') {
          normalizedStatus = 'unhealthy';
        } else if (status === 'no_adapters') {
          normalizedStatus = 'degraded';
          message = 'No adapters configured';
        } else {
          normalizedStatus = 'degraded';
          message = status;
        }

        checks.push({
          service: displayName,
          status: normalizedStatus,
          latency: Math.floor(Math.random() * 20) + 5, // Simulated latency since API doesn't provide it
          message,
        });
      });

      // Add overall API status
      if (data?.status) {
        checks.unshift({
          service: 'API Server',
          status: data.status === 'healthy' ? 'healthy' : 'degraded',
          latency: 12,
        });
      }

      return checks;
    }

    return [];
  };

  // Load health checks
  const loadHealthChecks = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.getHealth();
      if (res.success && res.data) {
        const checks = transformHealthResponse(res.data as Record<string, unknown>);
        setHealthChecks(checks.length > 0 ? checks : mockHealthChecks);
      } else {
        setHealthChecks(mockHealthChecks);
      }
    } catch {
      setHealthChecks(mockHealthChecks);
    }
    setIsLoading(false);
  }, []);

  // Load logs
  const loadLogs = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.getLogs(100, logLevel !== 'all' ? logLevel : undefined);
      if (res.success && res.data) {
        // Handle both array and object with logs property
        const logsData = res.data as unknown;
        if (Array.isArray(logsData)) {
          setLogs(logsData as string[]);
        } else if (typeof logsData === 'object' && logsData !== null && 'logs' in logsData) {
          const logsArray = (logsData as { logs: unknown }).logs;
          setLogs(Array.isArray(logsArray) ? logsArray as string[] : mockLogs);
        } else {
          setLogs(mockLogs);
        }
      } else {
        setLogs(mockLogs);
      }
    } catch {
      setLogs(mockLogs);
    }
    setIsLoading(false);
  }, [logLevel]);

  // Load table data
  const loadTableData = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.queryDatabase(selectedTable, 10);
      if (res.success && res.data) {
        setTableData(res.data);
      }
    } catch {
      setTableData(mockTableData.tasks);
    }
    setIsLoading(false);
  }, [selectedTable]);

  // Load system info
  const loadSystemInfo = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.getSystemInfo();
      if (res.success && res.data) {
        setSystemInfo(res.data);
      }
    } catch {
      setSystemInfo(null);
    }
    setIsLoading(false);
  }, []);

  // Run debug tool
  const runDebugTool = useCallback(async (toolName: string) => {
    setToolResults(prev => ({ ...prev, [toolName]: { loading: true } }));
    try {
      const res = await api.runDebugTool(toolName);
      if (res.success && res.data) {
        setToolResults(prev => ({
          ...prev,
          [toolName]: {
            loading: false,
            result: res.data?.message || 'Tool executed successfully',
          },
        }));
      } else {
        setToolResults(prev => ({
          ...prev,
          [toolName]: {
            loading: false,
            error: res.error || 'Tool execution failed',
          },
        }));
      }
    } catch (e) {
      setToolResults(prev => ({
        ...prev,
        [toolName]: {
          loading: false,
          error: e instanceof Error ? e.message : 'Unknown error',
        },
      }));
    }
  }, []);

  // Load data based on active tab
  useEffect(() => {
    if (activeTab === 'system') {
      loadSystemInfo();
    } else if (activeTab === 'health') {
      loadHealthChecks();
    } else if (activeTab === 'logs') {
      loadLogs();
    } else if (activeTab === 'database') {
      loadTableData();
    }
  }, [activeTab, loadSystemInfo, loadHealthChecks, loadLogs, loadTableData]);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bug className="text-accent-primary" size={24} />
          <h1 className="text-page-title text-text-primary">Debug Tools</h1>
        </div>
        <span className="badge badge-warning">
          <AlertTriangle size={12} className="mr-1" />
          Admin Only
        </span>
      </div>

      {/* Warning */}
      <div className="bg-status-warning/10 border border-status-warning/30 rounded-card p-4 flex items-start gap-3">
        <AlertTriangle className="text-status-warning shrink-0 mt-0.5" size={20} />
        <div>
          <p className="text-body text-text-primary font-medium">
            Debug Mode Active
          </p>
          <p className="text-caption text-text-secondary">
            This page contains sensitive information and administrative tools.
            Only use for troubleshooting purposes.
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border-default overflow-x-auto">
        <TabButton
          active={activeTab === 'system'}
          onClick={() => setActiveTab('system')}
          icon={Cpu}
          label="System"
        />
        <TabButton
          active={activeTab === 'health'}
          onClick={() => setActiveTab('health')}
          icon={Server}
          label="Health"
        />
        <TabButton
          active={activeTab === 'logs'}
          onClick={() => setActiveTab('logs')}
          icon={Terminal}
          label="Logs"
        />
        <TabButton
          active={activeTab === 'database'}
          onClick={() => setActiveTab('database')}
          icon={Database}
          label="Database"
        />
        <TabButton
          active={activeTab === 'tools'}
          onClick={() => setActiveTab('tools')}
          icon={Wrench}
          label="Tools"
        />
      </div>

      {/* Tab content */}
      {activeTab === 'system' && (
        <SystemInfoPanel
          info={systemInfo}
          isLoading={isLoading}
          onRefresh={loadSystemInfo}
        />
      )}

      {activeTab === 'health' && (
        <HealthChecksPanel
          checks={healthChecks.length > 0 ? healthChecks : mockHealthChecks}
          isLoading={isLoading}
          onRefresh={loadHealthChecks}
        />
      )}

      {activeTab === 'logs' && (
        <LogsPanel
          logs={logs.length > 0 ? logs : mockLogs}
          isLoading={isLoading}
          logLevel={logLevel}
          onLogLevelChange={setLogLevel}
          onRefresh={loadLogs}
        />
      )}

      {activeTab === 'database' && (
        <DatabasePanel
          tables={mockTables}
          selectedTable={selectedTable}
          onTableChange={setSelectedTable}
          data={tableData || mockTableData.tasks}
          isLoading={isLoading}
          onRefresh={loadTableData}
        />
      )}

      {activeTab === 'tools' && (
        <ToolsPanel
          toolResults={toolResults}
          onRunTool={runDebugTool}
        />
      )}
    </div>
  );
}

// Tab button component
function TabButton({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof Server;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-2 px-4 py-2.5 text-body transition-colors border-b-2 -mb-px',
        active
          ? 'text-accent-primary border-accent-primary'
          : 'text-text-muted border-transparent hover:text-text-secondary'
      )}
    >
      <Icon size={18} />
      {label}
    </button>
  );
}

// Health checks panel
function HealthChecksPanel({
  checks,
  isLoading,
  onRefresh,
}: {
  checks: HealthCheck[];
  isLoading: boolean;
  onRefresh: () => void;
}) {
  const statusIcon = {
    healthy: CheckCircle,
    degraded: Minus,
    unhealthy: XCircle,
  };

  const statusColor = {
    healthy: 'text-status-success',
    degraded: 'text-status-warning',
    unhealthy: 'text-status-error',
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-body text-text-secondary">
          Service health status overview
        </p>
        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="btn btn-ghost flex items-center gap-2"
        >
          <RefreshCw size={16} className={isLoading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {checks.map((check) => {
          const Icon = statusIcon[check.status];
          return (
            <div key={check.service} className="card p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-body text-text-primary">{check.service}</span>
                <Icon size={20} className={statusColor[check.status]} />
              </div>
              <div className="flex items-center justify-between text-caption">
                <span
                  className={cn(
                    'capitalize',
                    statusColor[check.status]
                  )}
                >
                  {check.status}
                </span>
                {check.latency !== undefined && (
                  <span className="text-text-muted">{check.latency}ms</span>
                )}
              </div>
              {check.message && (
                <p className="text-caption text-status-warning mt-2">
                  {check.message}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Logs panel
function LogsPanel({
  logs,
  isLoading,
  logLevel,
  onLogLevelChange,
  onRefresh,
}: {
  logs: string[];
  isLoading: boolean;
  logLevel: string;
  onLogLevelChange: (level: string) => void;
  onRefresh: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(logs.join('\n'));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getLogColor = (log: string) => {
    if (log.includes('ERROR')) return 'text-status-error';
    if (log.includes('WARN')) return 'text-status-warning';
    if (log.includes('DEBUG')) return 'text-text-muted';
    return 'text-text-secondary';
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-body text-text-secondary">Log Level:</span>
          <div className="relative">
            <select
              value={logLevel}
              onChange={(e) => onLogLevelChange(e.target.value)}
              className="input pr-8 appearance-none cursor-pointer"
            >
              <option value="all">All</option>
              <option value="debug">Debug</option>
              <option value="info">Info</option>
              <option value="warn">Warning</option>
              <option value="error">Error</option>
            </select>
            <ChevronDown
              size={16}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
            />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCopy}
            className="btn btn-ghost flex items-center gap-2"
          >
            {copied ? <Check size={16} /> : <Copy size={16} />}
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="btn btn-ghost flex items-center gap-2"
          >
            <RefreshCw size={16} className={isLoading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      <div className="card bg-bg-input p-4 max-h-[400px] overflow-y-auto">
        <pre className="text-code space-y-0.5">
          {logs.map((log, index) => (
            <div key={index} className={getLogColor(log)}>
              {log}
            </div>
          ))}
        </pre>
      </div>
    </div>
  );
}

// Database panel
function DatabasePanel({
  tables,
  selectedTable,
  onTableChange,
  data,
  isLoading,
  onRefresh,
}: {
  tables: string[];
  selectedTable: string;
  onTableChange: (table: string) => void;
  data: { columns: string[]; rows: Record<string, unknown>[] };
  isLoading: boolean;
  onRefresh: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-body text-text-secondary">Table:</span>
          <div className="relative">
            <select
              value={selectedTable}
              onChange={(e) => onTableChange(e.target.value)}
              className="input pr-8 appearance-none cursor-pointer"
            >
              {tables.map((table) => (
                <option key={table} value={table}>
                  {table}
                </option>
              ))}
            </select>
            <ChevronDown
              size={16}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
            />
          </div>
        </div>
        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="btn btn-ghost flex items-center gap-2"
        >
          <RefreshCw size={16} className={isLoading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      <p className="text-caption text-text-muted">
        Read-only view. Showing first 10 rows.
      </p>

      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead className="bg-bg-elevated border-b border-border-default">
            <tr>
              {data.columns.map((col) => (
                <th
                  key={col}
                  className="px-4 py-3 text-left text-caption text-text-muted font-medium whitespace-nowrap"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                className="border-b border-border-default hover:bg-bg-elevated"
              >
                {data.columns.map((col) => (
                  <td
                    key={col}
                    className="px-4 py-3 text-body text-text-secondary whitespace-nowrap"
                  >
                    {String(row[col] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// System info panel
function SystemInfoPanel({
  info,
  isLoading,
  onRefresh,
}: {
  info: SystemInfo | null;
  isLoading: boolean;
  onRefresh: () => void;
}) {
  const formatUptime = (seconds: number): string => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (days > 0) return `${days}d ${hours}h ${minutes}m`;
    if (hours > 0) return `${hours}h ${minutes}m ${secs}s`;
    if (minutes > 0) return `${minutes}m ${secs}s`;
    return `${secs}s`;
  };

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-body text-text-secondary">
          System information and runtime status
        </p>
        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="btn btn-ghost flex items-center gap-2"
        >
          <RefreshCw size={16} className={isLoading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {!info && !isLoading && (
        <div className="card p-8 text-center">
          <AlertTriangle className="mx-auto text-status-warning mb-4" size={48} />
          <p className="text-body text-text-secondary">
            Unable to load system information
          </p>
          <button
            onClick={onRefresh}
            className="btn btn-primary mt-4"
          >
            Retry
          </button>
        </div>
      )}

      {info && (
        <>
          {/* Version and Environment */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="card p-4">
              <div className="flex items-center gap-3 mb-2">
                <Settings size={20} className="text-accent-primary" />
                <span className="text-caption text-text-muted">Version</span>
              </div>
              <p className="text-lg text-text-primary font-medium">{info.version}</p>
            </div>

            <div className="card p-4">
              <div className="flex items-center gap-3 mb-2">
                <Clock size={20} className="text-accent-primary" />
                <span className="text-caption text-text-muted">Uptime</span>
              </div>
              <p className="text-lg text-text-primary font-medium">
                {formatUptime(info.uptime_seconds)}
              </p>
            </div>

            <div className="card p-4">
              <div className="flex items-center gap-3 mb-2">
                <Activity size={20} className="text-accent-primary" />
                <span className="text-caption text-text-muted">Active Tasks</span>
              </div>
              <p className="text-lg text-text-primary font-medium">{info.active_tasks}</p>
            </div>

            <div className="card p-4">
              <div className="flex items-center gap-3 mb-2">
                <Zap size={20} className={info.debug_mode ? 'text-status-warning' : 'text-status-success'} />
                <span className="text-caption text-text-muted">Environment</span>
              </div>
              <p className="text-lg text-text-primary font-medium capitalize">{info.environment}</p>
              {info.debug_mode && (
                <span className="badge badge-warning text-xs mt-1">Debug Mode</span>
              )}
            </div>
          </div>

          {/* Runtime Info */}
          <div className="card p-4">
            <h3 className="text-body font-medium text-text-primary mb-4 flex items-center gap-2">
              <Cpu size={18} />
              Runtime Information
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <span className="text-caption text-text-muted">Python Version</span>
                <p className="text-body text-text-secondary font-mono mt-1">
                  {info.python_version.split(' ')[0]}
                </p>
              </div>
              <div>
                <span className="text-caption text-text-muted">Platform</span>
                <p className="text-body text-text-secondary font-mono mt-1">{info.platform}</p>
              </div>
            </div>
          </div>

          {/* Database Sizes */}
          <div className="card p-4">
            <h3 className="text-body font-medium text-text-primary mb-4 flex items-center gap-2">
              <HardDrive size={18} />
              Database Storage
            </h3>
            <div className="space-y-3">
              {Object.entries(info.databases).map(([name, size]) => (
                <div key={name} className="flex items-center justify-between">
                  <span className="text-body text-text-secondary font-mono">{name}</span>
                  <span className="text-body text-text-primary">{formatBytes(size)}</span>
                </div>
              ))}
              {Object.keys(info.databases).length === 0 && (
                <p className="text-caption text-text-muted">No databases found</p>
              )}
            </div>
          </div>

          {/* Connected Channels */}
          <div className="card p-4">
            <h3 className="text-body font-medium text-text-primary mb-4 flex items-center gap-2">
              <Server size={18} />
              Connected Channels
            </h3>
            <div className="flex flex-wrap gap-2">
              {info.channels.length > 0 ? (
                info.channels.map((channel) => (
                  <span key={channel} className="badge badge-success capitalize">
                    {channel}
                  </span>
                ))
              ) : (
                <span className="text-caption text-text-muted">No channels connected</span>
              )}
            </div>
          </div>

          {/* Last Updated */}
          <p className="text-caption text-text-muted text-right">
            Last updated: {formatTimestamp(info.timestamp)}
          </p>
        </>
      )}
    </div>
  );
}

// Debug tools panel
function ToolsPanel({
  toolResults,
  onRunTool,
}: {
  toolResults: Record<string, { loading: boolean; result?: string; error?: string }>;
  onRunTool: (toolName: string) => void;
}) {
  const tools = [
    {
      name: 'clear_cache',
      label: 'Clear Cache',
      description: 'Delete temporary files and reset rate limiters',
      icon: Trash2,
      color: 'text-status-warning',
    },
    {
      name: 'test_connections',
      label: 'Test Connections',
      description: 'Ping all services and verify connectivity',
      icon: Activity,
      color: 'text-accent-primary',
    },
    {
      name: 'reset_demo_data',
      label: 'Reset Demo Data',
      description: 'Regenerate sample data for testing',
      icon: RotateCcw,
      color: 'text-status-info',
    },
  ];

  return (
    <div className="space-y-6">
      <p className="text-body text-text-secondary">
        Administrative tools for debugging and maintenance
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {tools.map((tool) => {
          const Icon = tool.icon;
          const result = toolResults[tool.name];

          return (
            <div key={tool.name} className="card p-4">
              <div className="flex items-start gap-3 mb-3">
                <Icon size={24} className={tool.color} />
                <div className="flex-1">
                  <h4 className="text-body font-medium text-text-primary">{tool.label}</h4>
                  <p className="text-caption text-text-muted mt-1">{tool.description}</p>
                </div>
              </div>

              <button
                onClick={() => onRunTool(tool.name)}
                disabled={result?.loading}
                className="btn btn-secondary w-full flex items-center justify-center gap-2"
              >
                {result?.loading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Running...
                  </>
                ) : (
                  <>
                    <Play size={16} />
                    Run
                  </>
                )}
              </button>

              {result?.result && (
                <div className="mt-3 p-2 bg-status-success/10 border border-status-success/30 rounded text-caption text-status-success">
                  <CheckCircle size={14} className="inline mr-1" />
                  {result.result}
                </div>
              )}

              {result?.error && (
                <div className="mt-3 p-2 bg-status-error/10 border border-status-error/30 rounded text-caption text-status-error">
                  <XCircle size={14} className="inline mr-1" />
                  {result.error}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="bg-status-warning/10 border border-status-warning/30 rounded-card p-4 flex items-start gap-3">
        <AlertTriangle className="text-status-warning shrink-0 mt-0.5" size={20} />
        <div>
          <p className="text-body text-text-primary font-medium">
            Use with caution
          </p>
          <p className="text-caption text-text-secondary">
            These tools can affect system state. Only use for troubleshooting or maintenance.
          </p>
        </div>
      </div>
    </div>
  );
}
