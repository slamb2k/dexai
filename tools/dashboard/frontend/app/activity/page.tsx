'use client';

import { useEffect, useState, useCallback } from 'react';
import { ActivityFeed, ActivityItem, ActivityType } from '@/components/activity-feed';
import { useActivityStore } from '@/lib/store';
import { api } from '@/lib/api';
import { socketClient } from '@/lib/socket';
import { cn, formatDate } from '@/lib/utils';
import {
  Search,
  Filter,
  RefreshCw,
  Download,
  Wifi,
  WifiOff,
  ChevronDown,
  X,
} from 'lucide-react';

// Mock data for demo
const mockActivity: ActivityItem[] = [
  {
    id: '1',
    type: 'message',
    timestamp: new Date(Date.now() - 1 * 60 * 1000),
    summary: 'Received message from @user on Telegram',
    channel: 'Telegram',
  },
  {
    id: '2',
    type: 'system',
    timestamp: new Date(Date.now() - 2 * 60 * 1000),
    summary: 'Input sanitization passed',
  },
  {
    id: '3',
    type: 'llm',
    timestamp: new Date(Date.now() - 3 * 60 * 1000),
    summary: 'Claude API request sent (1,240 tokens)',
  },
  {
    id: '4',
    type: 'llm',
    timestamp: new Date(Date.now() - 4 * 60 * 1000),
    summary: 'Response received (342 tokens)',
  },
  {
    id: '5',
    type: 'message',
    timestamp: new Date(Date.now() - 5 * 60 * 1000),
    summary: 'Sent response to Telegram',
    channel: 'Telegram',
  },
  {
    id: '6',
    type: 'task',
    timestamp: new Date(Date.now() - 10 * 60 * 1000),
    summary: 'Task completed: Schedule dentist appointment',
  },
  {
    id: '7',
    type: 'error',
    timestamp: new Date(Date.now() - 15 * 60 * 1000),
    summary: 'API rate limit reached, retrying in 30s',
  },
  {
    id: '8',
    type: 'security',
    timestamp: new Date(Date.now() - 20 * 60 * 1000),
    summary: 'Session refreshed for user',
  },
  {
    id: '9',
    type: 'system',
    timestamp: new Date(Date.now() - 30 * 60 * 1000),
    summary: 'Context snapshot saved',
  },
  {
    id: '10',
    type: 'message',
    timestamp: new Date(Date.now() - 45 * 60 * 1000),
    summary: 'Received message from @user on Discord',
    channel: 'Discord',
  },
];

const typeOptions: { value: ActivityType | 'all'; label: string }[] = [
  { value: 'all', label: 'All Types' },
  { value: 'message', label: 'Messages' },
  { value: 'task', label: 'Tasks' },
  { value: 'system', label: 'System' },
  { value: 'llm', label: 'LLM' },
  { value: 'error', label: 'Errors' },
  { value: 'security', label: 'Security' },
];

export default function ActivityPage() {
  const { items, setItems, addItem, isConnected, setConnected, clearItems } =
    useActivityStore();
  const [isLoading, setIsLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState<ActivityType | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedItem, setSelectedItem] = useState<ActivityItem | null>(null);

  // Load initial activity
  useEffect(() => {
    const loadActivity = async () => {
      setIsLoading(true);

      try {
        const res = await api.getActivity({
          type: typeFilter !== 'all' ? typeFilter : undefined,
          search: searchQuery || undefined,
          limit: 50,
        });

        if (res.success && res.data) {
          setItems(
            res.data.events.map((e) => ({
              ...e,
              timestamp: new Date(e.timestamp),
            }))
          );
        }
      } catch {
        // Use mock data
        setItems(mockActivity);
      }

      setIsLoading(false);
    };

    loadActivity();
  }, [setItems, typeFilter, searchQuery]);

  // Set up WebSocket for live updates
  useEffect(() => {
    socketClient.connect();

    const unsubConnect = socketClient.onConnect(() => {
      setConnected(true);
    });

    const unsubDisconnect = socketClient.onDisconnect(() => {
      setConnected(false);
    });

    const unsubActivity = socketClient.onActivityNew((event) => {
      // Only add if matches current filter
      if (typeFilter === 'all' || event.type === typeFilter) {
        addItem({
          ...event,
          timestamp: new Date(event.timestamp),
        });
      }
    });

    return () => {
      unsubConnect();
      unsubDisconnect();
      unsubActivity();
    };
  }, [setConnected, addItem, typeFilter]);

  // Filter items
  const filteredItems = items.filter((item) => {
    if (typeFilter !== 'all' && item.type !== typeFilter) return false;
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        item.summary.toLowerCase().includes(query) ||
        item.channel?.toLowerCase().includes(query)
      );
    }
    return true;
  });

  const displayItems = filteredItems.length > 0 ? filteredItems : mockActivity;

  // Export to JSON
  const handleExport = useCallback(() => {
    const data = JSON.stringify(displayItems, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dexai-activity-${formatDate(new Date())}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [displayItems]);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-page-title text-text-primary">Activity</h1>
          {/* Live indicator */}
          <span
            className={cn(
              'inline-flex items-center gap-1.5 px-2 py-1 rounded text-caption',
              isConnected
                ? 'bg-status-success/10 text-status-success'
                : 'bg-status-error/10 text-status-error'
            )}
          >
            {isConnected ? <Wifi size={14} /> : <WifiOff size={14} />}
            {isConnected ? 'Live' : 'Disconnected'}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => clearItems()}
            className="btn btn-ghost text-caption"
          >
            Clear
          </button>
          <button onClick={handleExport} className="btn btn-secondary">
            <Download size={16} className="mr-2" />
            Export
          </button>
        </div>
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
            placeholder="Search activity..."
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
              onChange={(e) => setTypeFilter(e.target.value as ActivityType | 'all')}
              className="input pr-8 appearance-none cursor-pointer"
            >
              {typeOptions.map((opt) => (
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
      </div>

      {/* Activity count */}
      <p className="text-caption text-text-muted">
        Showing {displayItems.length} event{displayItems.length !== 1 ? 's' : ''}
        {isConnected && ' (live updates enabled)'}
      </p>

      {/* Activity feed */}
      <div className="card p-2">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw size={24} className="animate-spin text-text-muted" />
          </div>
        ) : (
          <ActivityFeed
            items={displayItems}
            maxItems={100}
            onItemClick={(item) => setSelectedItem(item)}
          />
        )}
      </div>

      {/* Activity detail modal */}
      {selectedItem && (
        <ActivityDetailModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
        />
      )}
    </div>
  );
}

// Activity detail modal
function ActivityDetailModal({
  item,
  onClose,
}: {
  item: ActivityItem;
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
      <div className="relative bg-bg-surface border border-border-default rounded-card shadow-card w-full max-w-lg animate-scale-in">
        {/* Header */}
        <div className="border-b border-border-default px-6 py-4 flex items-center justify-between">
          <h2 className="text-section-header text-text-primary">Event Details</h2>
          <button
            onClick={onClose}
            className="p-2 rounded-button hover:bg-bg-elevated transition-colors"
          >
            <X size={20} className="text-text-muted" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          <div>
            <h3 className="text-caption text-text-muted uppercase tracking-wider mb-1">
              Type
            </h3>
            <span
              className={cn(
                'badge',
                item.type === 'message' && 'badge-info',
                item.type === 'task' && 'badge-success',
                item.type === 'error' && 'badge-error',
                item.type === 'security' && 'badge-warning',
                (item.type === 'system' || item.type === 'llm') &&
                  'bg-text-muted/20 text-text-muted'
              )}
            >
              {item.type.toUpperCase()}
            </span>
          </div>

          <div>
            <h3 className="text-caption text-text-muted uppercase tracking-wider mb-1">
              Timestamp
            </h3>
            <p className="text-body text-text-secondary font-mono">
              {formatDate(item.timestamp)} {new Date(item.timestamp).toLocaleTimeString()}
            </p>
          </div>

          <div>
            <h3 className="text-caption text-text-muted uppercase tracking-wider mb-1">
              Summary
            </h3>
            <p className="text-body text-text-primary">{item.summary}</p>
          </div>

          {item.channel && (
            <div>
              <h3 className="text-caption text-text-muted uppercase tracking-wider mb-1">
                Channel
              </h3>
              <p className="text-body text-text-secondary">{item.channel}</p>
            </div>
          )}

          {item.details && (
            <div>
              <h3 className="text-caption text-text-muted uppercase tracking-wider mb-1">
                Details
              </h3>
              <pre className="text-code text-text-secondary bg-bg-input p-3 rounded overflow-x-auto">
                {item.details}
              </pre>
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
