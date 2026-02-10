'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, AuditEvent } from '@/lib/api';
import { cn, formatDate, formatTimestamp } from '@/lib/utils';
import {
  Shield,
  Filter,
  Download,
  RefreshCw,
  ChevronDown,
  X,
  CheckCircle,
  XCircle,
  Search,
  User,
  Key,
  Database,
  Settings,
  AlertTriangle,
  AlertCircle,
  Inbox,
} from 'lucide-react';

const isDemo = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

// Demo mode fallback data
const demoAuditEvents: AuditEvent[] = [
  {
    id: '1',
    eventType: 'auth.login',
    timestamp: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    userId: 'user_123',
    action: 'User logged in',
    status: 'success',
    ipAddress: '192.168.1.100',
  },
  {
    id: '2',
    eventType: 'auth.session_refresh',
    timestamp: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
    userId: 'user_123',
    action: 'Session token refreshed',
    status: 'success',
  },
  {
    id: '3',
    eventType: 'permission.denied',
    timestamp: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
    userId: 'user_456',
    action: 'Attempted to access admin panel',
    resource: '/debug',
    status: 'failure',
    details: 'Insufficient permissions',
  },
  {
    id: '4',
    eventType: 'config.change',
    timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    userId: 'user_123',
    action: 'Updated notification settings',
    resource: 'settings.notifications',
    status: 'success',
  },
  {
    id: '5',
    eventType: 'data.access',
    timestamp: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
    userId: 'system',
    action: 'Memory database accessed',
    resource: 'memory.db',
    status: 'success',
  },
  {
    id: '6',
    eventType: 'auth.logout',
    timestamp: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
    userId: 'user_789',
    action: 'User logged out',
    status: 'success',
  },
  {
    id: '7',
    eventType: 'auth.failed',
    timestamp: new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString(),
    action: 'Invalid credentials provided',
    status: 'failure',
    ipAddress: '10.0.0.50',
    details: 'Multiple failed attempts detected',
  },
];

const eventTypeOptions = [
  { value: 'all', label: 'All Events' },
  { value: 'auth', label: 'Authentication' },
  { value: 'permission', label: 'Authorization' },
  { value: 'data', label: 'Data Access' },
  { value: 'config', label: 'Configuration' },
];

const statusOptions = [
  { value: 'all', label: 'All Status' },
  { value: 'success', label: 'Success' },
  { value: 'failure', label: 'Failure' },
];

const eventTypeIcons: Record<string, typeof Shield> = {
  auth: Key,
  permission: Shield,
  data: Database,
  config: Settings,
};

export default function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isEmpty, setIsEmpty] = useState(false);
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedEvent, setSelectedEvent] = useState<AuditEvent | null>(null);

  // Load audit events
  useEffect(() => {
    const loadEvents = async () => {
      setIsLoading(true);
      setError(null);
      setIsEmpty(false);
      try {
        const res = await api.getAuditLog({
          eventType: typeFilter !== 'all' ? typeFilter : undefined,
          status: statusFilter !== 'all' ? statusFilter : undefined,
          limit: 50,
        });
        if (res.success && res.data) {
          // Map events and stringify details if it's an object
          const mappedEvents = res.data.events.map((e) => ({
            ...e,
            details: typeof e.details === 'object' && e.details !== null
              ? JSON.stringify(e.details, null, 2)
              : e.details,
          }));
          setEvents(mappedEvents);
          setIsEmpty(mappedEvents.length === 0);
        } else if (res.error) {
          throw new Error(res.error);
        }
      } catch (e) {
        const errorMsg = e instanceof Error ? e.message : 'Failed to load audit log';
        setError(errorMsg);
        // Only use demo data if explicitly in demo mode
        if (isDemo) {
          setEvents(demoAuditEvents);
        }
      }
      setIsLoading(false);
    };
    loadEvents();
  }, [typeFilter, statusFilter]);

  // Filter events
  const filteredEvents = events.filter((event) => {
    if (typeFilter !== 'all' && !event.eventType.startsWith(typeFilter)) return false;
    if (statusFilter !== 'all' && event.status !== statusFilter) return false;
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        event.action.toLowerCase().includes(query) ||
        event.userId?.toLowerCase().includes(query) ||
        event.resource?.toLowerCase().includes(query)
      );
    }
    return true;
  });

  const displayEvents = filteredEvents.length > 0 ? filteredEvents : (isDemo ? demoAuditEvents : []);

  // Export to JSON
  const handleExport = useCallback(() => {
    const data = JSON.stringify(displayEvents, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dexai-audit-${formatDate(new Date())}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [displayEvents]);

  // Get icon for event type
  const getEventIcon = (eventType: string) => {
    const category = eventType.split('.')[0];
    return eventTypeIcons[category] || AlertTriangle;
  };

  return (
    <div className="space-y-8 pt-4 animate-fade-in">
      {/* Error banner */}
      {error && !isDemo && (
        <div className="bg-status-error/10 border border-status-error/30 rounded-card px-4 py-3 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-status-error flex-shrink-0" />
          <p className="text-body text-status-error">{error}</p>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <Shield className="w-6 h-6 text-white/40" />
            <h1 className="text-2xl font-light tracking-wide text-white/90">Audit Log</h1>
          </div>
          <p className="text-xs text-white/40 mt-1 tracking-wide">Security events and access history</p>
        </div>
        <button onClick={handleExport} className="btn btn-secondary">
          <Download size={16} className="mr-2" />
          Export
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted"
          />
          <input
            type="text"
            placeholder="Search events..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input w-full pl-9"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-bg-elevated rounded"
            >
              <X size={14} className="text-text-muted" />
            </button>
          )}
        </div>

        {/* Type filter */}
        <div className="flex items-center gap-2">
          <Filter size={16} className="text-text-muted" />
          <div className="relative">
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="input pr-8 appearance-none cursor-pointer"
            >
              {eventTypeOptions.map((opt) => (
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

        {/* Status filter */}
        <div className="relative">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
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
      </div>

      {/* Event count */}
      <p className="text-caption text-text-muted">
        Showing {displayEvents.length} event{displayEvents.length !== 1 ? 's' : ''}
      </p>

      {/* Events table */}
      <div className="card overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw size={24} className="animate-spin text-text-muted" />
          </div>
        ) : displayEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-text-muted">
            <Inbox size={48} className="mb-4 opacity-50" />
            <p className="text-body">No audit events</p>
            <p className="text-caption">Security events will appear here as they occur</p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-bg-elevated border-b border-border-default">
              <tr>
                <th className="px-4 py-3 text-left text-caption text-text-muted font-medium">
                  Timestamp
                </th>
                <th className="px-4 py-3 text-left text-caption text-text-muted font-medium">
                  Event
                </th>
                <th className="px-4 py-3 text-left text-caption text-text-muted font-medium">
                  User
                </th>
                <th className="px-4 py-3 text-left text-caption text-text-muted font-medium">
                  Action
                </th>
                <th className="px-4 py-3 text-left text-caption text-text-muted font-medium">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {displayEvents.map((event) => {
                const Icon = getEventIcon(event.eventType);
                return (
                  <tr
                    key={event.id}
                    onClick={() => setSelectedEvent(event)}
                    className="border-b border-border-default hover:bg-bg-elevated cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 text-caption text-text-muted font-mono whitespace-nowrap">
                      {formatTimestamp(event.timestamp)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Icon size={16} className="text-text-muted" />
                        <span className="text-body text-text-secondary">
                          {event.eventType}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <User size={14} className="text-text-muted" />
                        <span className="text-body text-text-secondary">
                          {event.userId || 'anonymous'}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-body text-text-secondary max-w-xs truncate">
                      {event.action}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          'inline-flex items-center gap-1 badge',
                          event.status === 'success'
                            ? 'badge-success'
                            : 'badge-error'
                        )}
                      >
                        {event.status === 'success' ? (
                          <CheckCircle size={12} />
                        ) : (
                          <XCircle size={12} />
                        )}
                        {event.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Event detail modal */}
      {selectedEvent && (
        <AuditDetailModal
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}
    </div>
  );
}

// Audit detail modal
function AuditDetailModal({
  event,
  onClose,
}: {
  event: AuditEvent;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative bg-bg-surface border border-border-default rounded-card shadow-card w-full max-w-lg animate-scale-in">
        <div className="border-b border-border-default px-6 py-4 flex items-center justify-between">
          <h2 className="text-section-header text-text-primary">Audit Event</h2>
          <button
            onClick={onClose}
            className="p-2 rounded-button hover:bg-bg-elevated transition-colors"
          >
            <X size={20} className="text-text-muted" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <DetailRow label="Event Type" value={event.eventType} />
          <DetailRow
            label="Timestamp"
            value={`${formatDate(event.timestamp)} ${formatTimestamp(event.timestamp)}`}
          />
          <DetailRow label="User" value={event.userId || 'anonymous'} />
          <DetailRow label="Action" value={event.action} />
          {event.resource && (
            <DetailRow label="Resource" value={event.resource} />
          )}
          <DetailRow
            label="Status"
            value={
              <span
                className={cn(
                  'badge',
                  event.status === 'success' ? 'badge-success' : 'badge-error'
                )}
              >
                {event.status}
              </span>
            }
          />
          {event.ipAddress && (
            <DetailRow label="IP Address" value={event.ipAddress} />
          )}
          {event.details && (
            <div>
              <h3 className="text-caption text-text-muted uppercase tracking-wider mb-1">
                Details
              </h3>
              <pre className="text-code text-text-secondary bg-bg-input p-3 rounded overflow-x-auto">
                {event.details}
              </pre>
            </div>
          )}
        </div>

        <div className="border-t border-border-default px-6 py-4">
          <button onClick={onClose} className="btn btn-secondary">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function DetailRow({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-caption text-text-muted uppercase tracking-wider mb-1">
        {label}
      </h3>
      <div className="text-body text-text-primary">{value}</div>
    </div>
  );
}
