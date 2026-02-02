'use client';

import { cn } from '@/lib/utils';
import { LucideIcon, TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string | number;
  icon?: LucideIcon;
  trend?: {
    value: number;
    direction: 'up' | 'down' | 'neutral';
  };
  sparklineData?: number[];
  className?: string;
}

export function StatCard({
  label,
  value,
  icon: Icon,
  trend,
  sparklineData,
  className,
}: StatCardProps) {
  return (
    <div
      className={cn(
        'card p-4 flex flex-col gap-3',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-caption text-text-muted uppercase tracking-wider">
          {label}
        </span>
        {Icon && (
          <Icon size={18} className="text-text-muted" />
        )}
      </div>

      {/* Value */}
      <div className="flex items-end justify-between">
        <span className="text-page-title text-text-primary">
          {value}
        </span>

        {/* Trend indicator */}
        {trend && (
          <div
            className={cn(
              'flex items-center gap-1 text-caption',
              trend.direction === 'up' && 'text-status-success',
              trend.direction === 'down' && 'text-status-error',
              trend.direction === 'neutral' && 'text-text-muted'
            )}
          >
            {trend.direction === 'up' && <TrendingUp size={14} />}
            {trend.direction === 'down' && <TrendingDown size={14} />}
            {trend.direction === 'neutral' && <Minus size={14} />}
            <span>{Math.abs(trend.value)}%</span>
          </div>
        )}
      </div>

      {/* Sparkline */}
      {sparklineData && sparklineData.length > 0 && (
        <Sparkline data={sparklineData} />
      )}
    </div>
  );
}

// Simple sparkline component
function Sparkline({ data }: { data: number[] }) {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const height = 30;
  const width = 100;
  const padding = 2;

  const points = data.map((value, index) => {
    const x = (index / (data.length - 1)) * (width - padding * 2) + padding;
    const y = height - ((value - min) / range) * (height - padding * 2) - padding;
    return `${x},${y}`;
  }).join(' ');

  // Create area fill path
  const areaPath = `M ${padding},${height - padding} L ${points} L ${width - padding},${height - padding} Z`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full h-[30px] mt-1"
      preserveAspectRatio="none"
    >
      {/* Area fill */}
      <path
        d={areaPath}
        fill="url(#sparkline-gradient)"
        opacity={0.3}
      />
      {/* Line */}
      <polyline
        points={points}
        fill="none"
        stroke="var(--accent-primary)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Gradient definition */}
      <defs>
        <linearGradient id="sparkline-gradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent-primary)" />
          <stop offset="100%" stopColor="transparent" />
        </linearGradient>
      </defs>
    </svg>
  );
}

// Variant: Stat card with colored accent
interface AccentStatCardProps extends StatCardProps {
  accentColor?: 'blue' | 'green' | 'amber' | 'red' | 'cyan' | 'purple';
}

export function AccentStatCard({
  accentColor = 'blue',
  ...props
}: AccentStatCardProps) {
  const colorMap = {
    blue: 'border-l-accent-primary',
    green: 'border-l-status-success',
    amber: 'border-l-status-warning',
    red: 'border-l-status-error',
    cyan: 'border-l-accent-secondary',
    purple: 'border-l-purple-500',
  };

  return (
    <StatCard
      {...props}
      className={cn('border-l-4', colorMap[accentColor], props.className)}
    />
  );
}
