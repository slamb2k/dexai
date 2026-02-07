'use client';

import { Zap } from 'lucide-react';
import { cn } from '@/lib/utils';

export type EnergyLevel = 'low' | 'medium' | 'high';

interface EnergySelectorProps {
  value: EnergyLevel;
  onChange: (level: EnergyLevel) => void;
  className?: string;
  compact?: boolean;
}

const energyOptions: {
  level: EnergyLevel;
  label: string;
  shortLabel: string;
  description: string;
  bolts: number;
}[] = [
  {
    level: 'low',
    label: 'Low Energy',
    shortLabel: 'Low',
    description: 'Simple, quick tasks',
    bolts: 1,
  },
  {
    level: 'medium',
    label: 'Medium Energy',
    shortLabel: 'Med',
    description: 'Regular focus tasks',
    bolts: 2,
  },
  {
    level: 'high',
    label: 'High Energy',
    shortLabel: 'High',
    description: 'Deep work & complex tasks',
    bolts: 3,
  },
];

export function EnergySelector({
  value,
  onChange,
  className,
  compact = false,
}: EnergySelectorProps) {
  return (
    <div className={cn('crystal-card p-4', className)}>
      {!compact && (
        <div className="flex items-center gap-2 mb-3 text-caption text-text-muted">
          <Zap className="w-4 h-4" />
          <span>Energy Level</span>
        </div>
      )}

      <div className="flex gap-2">
        {energyOptions.map((option) => (
          <button
            key={option.level}
            onClick={() => onChange(option.level)}
            className={cn(
              'flex-1 flex flex-col items-center gap-1 px-3 py-2 rounded-xl transition-all duration-200',
              value === option.level
                ? 'bg-accent-muted border border-accent-primary'
                : 'bg-bg-surface border border-border-default hover:border-border-focus hover:bg-bg-hover'
            )}
          >
            {/* Energy bolts */}
            <div className="flex items-center gap-0.5">
              {[1, 2, 3].map((i) => (
                <Zap
                  key={i}
                  className={cn(
                    'w-4 h-4 transition-all duration-200',
                    i <= option.bolts
                      ? value === option.level
                        ? option.level === 'low'
                          ? 'text-energy-low fill-energy-low'
                          : option.level === 'medium'
                          ? 'text-energy-medium fill-energy-medium'
                          : 'text-energy-high fill-energy-high'
                        : 'text-text-muted'
                      : 'text-text-disabled opacity-30'
                  )}
                />
              ))}
            </div>
            {/* Label */}
            <span
              className={cn(
                'text-caption font-medium',
                value === option.level ? 'text-text-primary' : 'text-text-secondary'
              )}
            >
              {compact ? option.shortLabel : option.label}
            </span>
          </button>
        ))}
      </div>

      {/* Selected description */}
      {!compact && (
        <p className="text-caption text-text-muted mt-3 text-center">
          {energyOptions.find((o) => o.level === value)?.description}
        </p>
      )}
    </div>
  );
}

// Inline version for dashboard widgets
export function EnergyIndicator({
  level,
  showLabel = true,
  className,
}: {
  level: EnergyLevel;
  showLabel?: boolean;
  className?: string;
}) {
  const config = {
    low: { bolts: 1, color: 'text-energy-low', label: 'Low Energy' },
    medium: { bolts: 2, color: 'text-energy-medium', label: 'Medium Energy' },
    high: { bolts: 3, color: 'text-energy-high', label: 'High Energy' },
  };

  const { bolts, color, label } = config[level];

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="flex items-center gap-0.5">
        {[1, 2, 3].map((i) => (
          <Zap
            key={i}
            className={cn(
              'w-4 h-4',
              i <= bolts ? `${color} fill-current` : 'text-text-disabled opacity-30'
            )}
          />
        ))}
      </div>
      {showLabel && (
        <span className={cn('text-caption', color)}>{label}</span>
      )}
    </div>
  );
}
