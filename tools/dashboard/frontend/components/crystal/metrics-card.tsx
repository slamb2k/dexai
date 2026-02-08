'use client';

import { ReactNode } from 'react';
import { LucideIcon } from 'lucide-react';
import { CrystalCard } from './crystal-card';
import { cn } from '@/lib/utils';

interface MetricsCardProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  sub?: string;
  trend?: {
    value: number;
    direction: 'up' | 'down' | 'neutral';
  };
  className?: string;
}

export function MetricsCard({
  icon: Icon,
  label,
  value,
  sub,
  trend,
  className,
}: MetricsCardProps) {
  return (
    <CrystalCard className={cn('relative overflow-hidden', className)}>
      {/* Subtle glow effect */}
      <div className="absolute -top-12 -right-12 w-24 h-24 bg-white/[0.02] rounded-full blur-2xl" />

      <div className="relative">
        {/* Header with icon and subtitle */}
        <div className="flex items-start justify-between mb-4">
          <div className="p-2 rounded-xl bg-white/[0.04] border border-white/[0.06]">
            <Icon className="w-5 h-5 text-white/40" />
          </div>
          {sub && (
            <span className="text-xs text-white/20 tracking-wider uppercase">{sub}</span>
          )}
        </div>

        {/* Main value */}
        <div className="text-4xl font-extralight text-white/90 mb-1 tracking-tight">
          {value}
        </div>

        {/* Label and trend */}
        <div className="flex items-center justify-between">
          <span className="text-sm text-white/40">{label}</span>
          {trend && (
            <span
              className={cn(
                'text-xs font-medium',
                trend.direction === 'up' && 'text-emerald-400',
                trend.direction === 'down' && 'text-red-400',
                trend.direction === 'neutral' && 'text-white/40'
              )}
            >
              {trend.direction === 'up' && '+'}
              {trend.direction === 'down' && '-'}
              {trend.value}%
            </span>
          )}
        </div>
      </div>
    </CrystalCard>
  );
}

// Compact variant for smaller displays
interface MetricsCardCompactProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  className?: string;
}

export function MetricsCardCompact({
  icon: Icon,
  label,
  value,
  className,
}: MetricsCardCompactProps) {
  return (
    <div
      className={cn(
        'flex items-center gap-3 p-3 rounded-xl',
        'bg-white/[0.02] border border-white/[0.06]',
        className
      )}
    >
      <Icon className="w-4 h-4 text-white/40 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-white/90 truncate">{value}</div>
        <div className="text-xs text-white/40 truncate">{label}</div>
      </div>
    </div>
  );
}
