'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, HealthCheck } from '@/lib/api';
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
  const [activeTab, setActiveTab] = useState<'health' | 'logs' | 'database'>('health');
  const [healthChecks, setHealthChecks] = useState<HealthCheck[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedTable, setSelectedTable] = useState(mockTables[0]);
  const [tableData, setTableData] = useState<{
    columns: string[];
    rows: Record<string, unknown>[];
  } | null>(null);
  const [logLevel, setLogLevel] = useState('all');

  // Load health checks
  const loadHealthChecks = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.getHealth();
      if (res.success && res.data) {
        setHealthChecks(res.data.checks);
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
        setLogs(res.data.logs);
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

  // Load data based on active tab
  useEffect(() => {
    if (activeTab === 'health') {
      loadHealthChecks();
    } else if (activeTab === 'logs') {
      loadLogs();
    } else if (activeTab === 'database') {
      loadTableData();
    }
  }, [activeTab, loadHealthChecks, loadLogs, loadTableData]);

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
      <div className="flex gap-1 border-b border-border-default">
        <TabButton
          active={activeTab === 'health'}
          onClick={() => setActiveTab('health')}
          icon={Server}
          label="Health Checks"
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
      </div>

      {/* Tab content */}
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
