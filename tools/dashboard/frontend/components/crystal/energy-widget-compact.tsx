'use client';

import { useEffect, useState } from 'react';
import { Zap, ChevronDown, ChevronUp } from 'lucide-react';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

type EnergyLevel = 'low' | 'medium' | 'high';

const energyConfig = {
  low: {
    label: 'Low Energy',
    description: 'Simple, quick tasks',
    color: 'text-teal-400',
    bgColor: 'bg-teal-500/10',
    borderColor: 'border-teal-500/20',
    activeBg: 'bg-teal-500/15',
    activeBorder: 'border-teal-500/30',
  },
  medium: {
    label: 'Medium Energy',
    description: 'Regular focus tasks',
    color: 'text-emerald-400',
    bgColor: 'bg-emerald-500/10',
    borderColor: 'border-emerald-500/20',
    activeBg: 'bg-emerald-500/15',
    activeBorder: 'border-emerald-500/30',
  },
  high: {
    label: 'High Energy',
    description: 'Deep work & complex tasks',
    color: 'text-green-400',
    bgColor: 'bg-green-500/10',
    borderColor: 'border-green-500/20',
    activeBg: 'bg-green-500/15',
    activeBorder: 'border-green-500/30',
  },
};

interface EnergyWidgetCompactProps {
  className?: string;
}

export function EnergyWidgetCompact({ className }: EnergyWidgetCompactProps) {
  const [energyLevel, setEnergyLevel] = useState<EnergyLevel>('medium');
  const [isLoading, setIsLoading] = useState(true);
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    const fetchEnergy = async () => {
      try {
        const res = await api.getEnergyLevel();
        if (res.success && res.data) {
          setEnergyLevel(res.data.level as EnergyLevel);
        }
      } catch (e) {
        console.error('Failed to fetch energy level:', e);
      }
      setIsLoading(false);
    };

    fetchEnergy();
  }, []);

  const handleEnergyChange = async (level: EnergyLevel) => {
    setEnergyLevel(level);
    try {
      await api.setEnergyLevel(level);
    } catch (e) {
      console.error('Failed to save energy level:', e);
    }
  };

  const config = energyConfig[energyLevel];

  return (
    <div className={cn('rounded-xl overflow-hidden', className)}>
      {/* Header - clickable to expand */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={cn(
          'w-full flex items-center justify-between p-3',
          'bg-white/[0.02] border border-white/[0.06]',
          'hover:bg-white/[0.04] hover:border-white/[0.08]',
          'transition-all duration-200',
          isExpanded && 'rounded-b-none border-b-0',
          !isExpanded && 'rounded-xl',
          isLoading && 'animate-pulse'
        )}
      >
        <div className="flex items-center gap-3">
          {/* Energy Icon with colored background */}
          <div
            className={cn(
              'p-2 rounded-lg border',
              config.bgColor,
              config.borderColor
            )}
          >
            <Zap className={cn('w-4 h-4', config.color)} />
          </div>

          {/* Labels */}
          <div className="text-left">
            <p className="text-sm font-medium text-white/80">{config.label}</p>
            <p className="text-xs text-white/40">{config.description}</p>
          </div>
        </div>

        {/* Expand/collapse indicator */}
        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-white/40" />
        ) : (
          <ChevronDown className="w-4 h-4 text-white/40" />
        )}
      </button>

      {/* Expanded content - energy level selector */}
      <div
        className={cn(
          'overflow-hidden transition-all duration-200',
          isExpanded ? 'max-h-40 opacity-100' : 'max-h-0 opacity-0'
        )}
      >
        <div className="p-3 pt-0 bg-white/[0.02] border border-t-0 border-white/[0.06] rounded-b-xl">
          <div className="flex gap-2 pt-3 border-t border-white/[0.06]">
            {(Object.keys(energyConfig) as EnergyLevel[]).map((level) => {
              const levelConfig = energyConfig[level];
              const isSelected = energyLevel === level;

              return (
                <button
                  key={level}
                  onClick={() => handleEnergyChange(level)}
                  className={cn(
                    'flex-1 flex flex-col items-center gap-1 px-2 py-2 rounded-lg',
                    'transition-all duration-200 border',
                    isSelected
                      ? cn(levelConfig.activeBg, levelConfig.activeBorder)
                      : 'bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.04] hover:border-white/[0.10]'
                  )}
                >
                  <Zap
                    className={cn(
                      'w-4 h-4',
                      isSelected ? levelConfig.color : 'text-white/40'
                    )}
                  />
                  <span
                    className={cn(
                      'text-xs font-medium',
                      isSelected ? 'text-white/90' : 'text-white/50'
                    )}
                  >
                    {level.charAt(0).toUpperCase() + level.slice(1)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
