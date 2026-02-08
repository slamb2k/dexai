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

const energyConfig = {
  low: {
    label: 'Low',
    fullLabel: 'Low Energy',
    description: 'Simple, quick tasks',
    bolts: 1,
    color: 'text-teal-400',
    fillColor: 'fill-teal-400',
    bgColor: 'bg-teal-400/10',
    borderColor: 'border-teal-400/30',
  },
  medium: {
    label: 'Med',
    fullLabel: 'Medium Energy',
    description: 'Regular focus tasks',
    bolts: 2,
    color: 'text-emerald-400',
    fillColor: 'fill-emerald-400',
    bgColor: 'bg-emerald-400/10',
    borderColor: 'border-emerald-400/30',
  },
  high: {
    label: 'High',
    fullLabel: 'High Energy',
    description: 'Deep work & complex tasks',
    bolts: 3,
    color: 'text-green-400',
    fillColor: 'fill-green-400',
    bgColor: 'bg-green-400/10',
    borderColor: 'border-green-400/30',
  },
};

export function EnergySelector({
  value,
  onChange,
  className,
  compact = false,
}: EnergySelectorProps) {
  const config = energyConfig[value];

  if (compact) {
    // Compact header version - pill-style selector
    return (
      <div
        className={cn(
          'flex items-center gap-1 p-1 rounded-xl',
          'bg-white/[0.03] border border-white/[0.06]',
          className
        )}
      >
        {(Object.keys(energyConfig) as EnergyLevel[]).map((level) => {
          const levelConfig = energyConfig[level];
          const isSelected = value === level;

          return (
            <button
              key={level}
              onClick={() => onChange(level)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
                'transition-all duration-200',
                isSelected
                  ? cn(levelConfig.bgColor, levelConfig.borderColor, 'border')
                  : 'hover:bg-white/[0.04]'
              )}
              title={levelConfig.description}
            >
              <div className="flex items-center">
                {[1, 2, 3].map((i) => (
                  <Zap
                    key={i}
                    className={cn(
                      'w-3 h-3 -ml-0.5 first:ml-0',
                      i <= levelConfig.bolts
                        ? isSelected
                          ? cn(levelConfig.color, levelConfig.fillColor)
                          : 'text-white/30'
                        : 'text-white/10'
                    )}
                  />
                ))}
              </div>
              <span
                className={cn(
                  'text-xs font-medium',
                  isSelected ? levelConfig.color : 'text-white/40'
                )}
              >
                {levelConfig.label}
              </span>
            </button>
          );
        })}
      </div>
    );
  }

  // Full version for settings/mobile menu
  return (
    <div
      className={cn(
        'p-4 rounded-2xl',
        'bg-white/[0.02] border border-white/[0.06]',
        className
      )}
    >
      <div className="flex items-center gap-2 mb-3 text-xs text-white/40">
        <Zap className="w-4 h-4" />
        <span>Energy Level</span>
      </div>

      <div className="flex gap-2">
        {(Object.keys(energyConfig) as EnergyLevel[]).map((level) => {
          const levelConfig = energyConfig[level];
          const isSelected = value === level;

          return (
            <button
              key={level}
              onClick={() => onChange(level)}
              className={cn(
                'flex-1 flex flex-col items-center gap-1.5 px-3 py-3 rounded-xl',
                'transition-all duration-200 border',
                isSelected
                  ? cn(levelConfig.bgColor, levelConfig.borderColor)
                  : 'bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.04] hover:border-white/[0.10]'
              )}
            >
              <div className="flex items-center gap-0.5">
                {[1, 2, 3].map((i) => (
                  <Zap
                    key={i}
                    className={cn(
                      'w-4 h-4',
                      i <= levelConfig.bolts
                        ? isSelected
                          ? cn(levelConfig.color, levelConfig.fillColor)
                          : 'text-white/40'
                        : 'text-white/20'
                    )}
                  />
                ))}
              </div>
              <span
                className={cn(
                  'text-sm font-medium',
                  isSelected ? 'text-white/90' : 'text-white/50'
                )}
              >
                {levelConfig.fullLabel}
              </span>
            </button>
          );
        })}
      </div>

      <p className="text-xs text-white/30 mt-3 text-center">{config.description}</p>
    </div>
  );
}

// Inline indicator version for dashboard widgets
export function EnergyIndicator({
  level,
  showLabel = true,
  className,
}: {
  level: EnergyLevel;
  showLabel?: boolean;
  className?: string;
}) {
  const config = energyConfig[level];

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="flex items-center gap-0.5">
        {[1, 2, 3].map((i) => (
          <Zap
            key={i}
            className={cn(
              'w-4 h-4',
              i <= config.bolts
                ? cn(config.color, config.fillColor)
                : 'text-white/20'
            )}
          />
        ))}
      </div>
      {showLabel && (
        <span className={cn('text-xs', config.color)}>{config.fullLabel}</span>
      )}
    </div>
  );
}
