'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp, LucideIcon } from 'lucide-react';
import { MetricsCard } from './metrics-card';
import { cn } from '@/lib/utils';

export interface MetricItem {
  icon: LucideIcon;
  label: string;
  value: string | number;
  sub?: string;
  trend?: {
    value: number;
    direction: 'up' | 'down' | 'neutral';
  };
}

interface ExpandableMetricsRowProps {
  metrics: MetricItem[];
  defaultExpanded?: boolean;
  className?: string;
}

export function ExpandableMetricsRow({
  metrics,
  defaultExpanded = false,
  className,
}: ExpandableMetricsRowProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  return (
    <div className={cn('w-full', className)}>
      {/* Collapsed State - Summary Pills */}
      <div
        className={cn(
          'overflow-hidden transition-all duration-300 ease-out',
          isExpanded ? 'max-h-0 opacity-0' : 'max-h-16 opacity-100'
        )}
      >
        <div className="flex items-center gap-3 p-2">
          {/* Metric Pills */}
          <div className="flex-1 flex items-center gap-2 overflow-x-auto scrollbar-hide">
            {metrics.map((metric, index) => (
              <MetricPill key={index} metric={metric} />
            ))}
          </div>

          {/* Expand Button */}
          <button
            onClick={() => setIsExpanded(true)}
            className={cn(
              'flex-shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-xl',
              'bg-white/[0.03] border border-white/[0.06]',
              'text-white/40 hover:text-white/60 hover:bg-white/[0.05]',
              'text-xs font-medium transition-all'
            )}
          >
            <ChevronDown className="w-3.5 h-3.5" />
            Details
          </button>
        </div>
      </div>

      {/* Expanded State - Full Cards */}
      <div
        className={cn(
          'overflow-hidden transition-all duration-300 ease-out',
          isExpanded ? 'max-h-[220px] opacity-100' : 'max-h-0 opacity-0'
        )}
      >
        <div className="space-y-4">
          {/* Collapse Button */}
          <div className="flex justify-end">
            <button
              onClick={() => setIsExpanded(false)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
                'text-white/40 hover:text-white/60',
                'text-xs transition-colors'
              )}
            >
              <ChevronUp className="w-3.5 h-3.5" />
              Collapse
            </button>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {metrics.map((metric, index) => (
              <MetricsCard
                key={index}
                icon={metric.icon}
                label={metric.label}
                value={metric.value}
                sub={metric.sub}
                trend={metric.trend}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

interface MetricPillProps {
  metric: MetricItem;
}

function MetricPill({ metric }: MetricPillProps) {
  const Icon = metric.icon;

  return (
    <div
      className={cn(
        'flex items-center gap-2 px-3 py-2 rounded-xl',
        'bg-white/[0.02] border border-white/[0.06]',
        'whitespace-nowrap flex-shrink-0'
      )}
    >
      <Icon className="w-4 h-4 text-white/40" />
      <span className="text-sm font-medium text-white/80">{metric.value}</span>
      <span className="text-xs text-white/40">{metric.label}</span>
      {metric.trend && (
        <span
          className={cn(
            'text-xs font-medium',
            metric.trend.direction === 'up' && 'text-emerald-400',
            metric.trend.direction === 'down' && 'text-red-400',
            metric.trend.direction === 'neutral' && 'text-white/40'
          )}
        >
          {metric.trend.direction === 'up' && '+'}
          {metric.trend.direction === 'down' && '-'}
          {metric.trend.value}%
        </span>
      )}
    </div>
  );
}
