'use client';

import { cn, formatTimestamp } from '@/lib/utils';
import {
  MessageSquare,
  ListTodo,
  Settings,
  AlertCircle,
  Bot,
  Zap,
  Shield,
} from 'lucide-react';
import { LucideIcon } from 'lucide-react';

export type ActivityType = 'message' | 'task' | 'system' | 'error' | 'llm' | 'security';

export interface ActivityItem {
  id: string;
  type: ActivityType;
  timestamp: Date | string;
  summary: string;
  channel?: string;
  details?: string;
}

interface ActivityFeedProps {
  items: ActivityItem[];
  maxItems?: number;
  showTimestamp?: boolean;
  onItemClick?: (item: ActivityItem) => void;
  className?: string;
}

const typeConfig: Record<
  ActivityType,
  { icon: LucideIcon; color: string; bgColor: string; label: string }
> = {
  message: {
    icon: MessageSquare,
    color: 'text-accent-primary',
    bgColor: 'bg-accent-primary/10',
    label: 'MESSAGE',
  },
  task: {
    icon: ListTodo,
    color: 'text-status-success',
    bgColor: 'bg-status-success/10',
    label: 'TASK',
  },
  system: {
    icon: Settings,
    color: 'text-text-muted',
    bgColor: 'bg-text-muted/10',
    label: 'SYSTEM',
  },
  error: {
    icon: AlertCircle,
    color: 'text-status-error',
    bgColor: 'bg-status-error/10',
    label: 'ERROR',
  },
  llm: {
    icon: Bot,
    color: 'text-accent-secondary',
    bgColor: 'bg-accent-secondary/10',
    label: 'LLM',
  },
  security: {
    icon: Shield,
    color: 'text-status-warning',
    bgColor: 'bg-status-warning/10',
    label: 'SECURITY',
  },
};

// Fallback for unknown types
const defaultConfig = {
  icon: Zap,
  color: 'text-text-muted',
  bgColor: 'bg-text-muted/10',
  label: 'UNKNOWN',
};

export function ActivityFeed({
  items,
  maxItems = 10,
  showTimestamp = true,
  onItemClick,
  className,
}: ActivityFeedProps) {
  const displayItems = items.slice(0, maxItems);

  if (displayItems.length === 0) {
    return (
      <div className={cn('text-center py-8', className)}>
        <Zap size={32} className="mx-auto text-text-muted mb-2" />
        <p className="text-body text-text-muted">No activity yet</p>
      </div>
    );
  }

  return (
    <div className={cn('space-y-1', className)}>
      {displayItems.map((item) => (
        <ActivityFeedItem
          key={item.id}
          item={item}
          showTimestamp={showTimestamp}
          onClick={onItemClick ? () => onItemClick(item) : undefined}
        />
      ))}
    </div>
  );
}

interface ActivityFeedItemProps {
  item: ActivityItem;
  showTimestamp?: boolean;
  onClick?: () => void;
}

function ActivityFeedItem({
  item,
  showTimestamp = true,
  onClick,
}: ActivityFeedItemProps) {
  const config = typeConfig[item.type] || defaultConfig;
  const Icon = config.icon;

  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={cn(
        'w-full flex items-start gap-3 px-3 py-2.5 rounded-button text-left transition-colors',
        onClick && 'hover:bg-bg-elevated cursor-pointer',
        !onClick && 'cursor-default'
      )}
    >
      {/* Timestamp */}
      {showTimestamp && (
        <span className="text-caption text-text-muted font-mono shrink-0 w-[70px]">
          {formatTimestamp(item.timestamp)}
        </span>
      )}

      {/* Type badge */}
      <span
        className={cn(
          'inline-flex items-center gap-1 px-2 py-0.5 rounded text-caption font-medium shrink-0',
          config.bgColor,
          config.color
        )}
      >
        <Icon size={12} />
        <span className="hidden sm:inline">{config.label}</span>
      </span>

      {/* Summary */}
      <span className="text-body text-text-secondary flex-1 truncate">
        {item.summary}
      </span>

      {/* Channel indicator */}
      {item.channel && (
        <span className="text-caption text-text-muted shrink-0">
          {item.channel}
        </span>
      )}
    </button>
  );
}

// Compact variant for smaller spaces
interface CompactActivityFeedProps {
  items: ActivityItem[];
  maxItems?: number;
  className?: string;
}

export function CompactActivityFeed({
  items,
  maxItems = 5,
  className,
}: CompactActivityFeedProps) {
  const displayItems = items.slice(0, maxItems);

  if (displayItems.length === 0) {
    return (
      <p className={cn('text-caption text-text-muted text-center py-4', className)}>
        No recent activity
      </p>
    );
  }

  return (
    <div className={cn('space-y-2', className)}>
      {displayItems.map((item) => {
        const config = typeConfig[item.type] || defaultConfig;
        return (
          <div key={item.id} className="flex items-center gap-2">
            <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', config.bgColor.replace('/10', ''))} />
            <span className="text-caption text-text-muted shrink-0">
              {formatTimestamp(item.timestamp)}
            </span>
            <span className="text-caption text-text-secondary truncate">
              {item.summary}
            </span>
          </div>
        );
      })}
    </div>
  );
}
