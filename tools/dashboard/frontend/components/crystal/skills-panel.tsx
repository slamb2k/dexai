'use client';

import { useEffect, useState } from 'react';
import { Sparkles, Circle, ExternalLink, RefreshCw } from 'lucide-react';
import { CrystalCard, CrystalCardHeader, CrystalCardContent } from './crystal-card';
import { api, Skill } from '@/lib/api';
import { cn } from '@/lib/utils';

interface SkillsPanelProps {
  maxDisplay?: number;
  className?: string;
}

export function SkillsPanel({ maxDisplay = 4, className }: SkillsPanelProps) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSkills = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getSkills();
      if (res.success && res.data) {
        setSkills(res.data.skills);
      } else {
        setError(res.error || 'Failed to load skills');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load skills');
    }
    setIsLoading(false);
  };

  useEffect(() => {
    fetchSkills();
  }, []);

  const displayedSkills = skills.slice(0, maxDisplay);
  const remainingCount = Math.max(0, skills.length - maxDisplay);

  return (
    <CrystalCard padding="none" className={className}>
      <div className="p-6">
        <CrystalCardHeader
          icon={<Sparkles className="w-5 h-5" />}
          title="Active Skills"
          subtitle={`${skills.length} available`}
          action={
            <button
              onClick={fetchSkills}
              disabled={isLoading}
              className="p-1.5 rounded-lg hover:bg-white/[0.06] transition-colors"
            >
              <RefreshCw className={cn('w-4 h-4 text-white/40', isLoading && 'animate-spin')} />
            </button>
          }
        />
      </div>

      <CrystalCardContent className="px-6 pb-6 pt-0">
        {error ? (
          <div className="text-center py-4">
            <p className="text-sm text-red-400/80">{error}</p>
            <button
              onClick={fetchSkills}
              className="mt-2 text-xs text-white/40 hover:text-white/60 transition-colors"
            >
              Try again
            </button>
          </div>
        ) : isLoading ? (
          <div className="grid grid-cols-2 gap-3">
            {[...Array(4)].map((_, i) => (
              <div
                key={i}
                className="h-16 rounded-xl bg-white/[0.02] animate-pulse"
              />
            ))}
          </div>
        ) : skills.length === 0 ? (
          <div className="text-center py-6">
            <Sparkles className="w-8 h-8 text-white/20 mx-auto mb-2" />
            <p className="text-sm text-white/40">No skills installed</p>
            <p className="text-xs text-white/20 mt-1">
              Add skills to ~/.claude/skills/
            </p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              {displayedSkills.map((skill) => (
                <SkillItem key={skill.name} skill={skill} />
              ))}
            </div>
            {remainingCount > 0 && (
              <button className="w-full mt-3 py-2 text-xs text-white/40 hover:text-white/60 transition-colors">
                +{remainingCount} more skills
              </button>
            )}
          </>
        )}
      </CrystalCardContent>
    </CrystalCard>
  );
}

function SkillItem({ skill }: { skill: Skill }) {
  const isRunning = skill.status === 'running';

  return (
    <div
      className={cn(
        'group relative p-3 rounded-xl transition-all duration-200',
        'bg-white/[0.02] border border-white/[0.04]',
        'hover:bg-white/[0.04] hover:border-white/[0.08]'
      )}
    >
      <div className="flex items-start gap-2">
        {/* Status indicator */}
        <div className="relative mt-1">
          <Circle
            className={cn(
              'w-2 h-2',
              isRunning ? 'text-emerald-400 fill-emerald-400' : 'text-white/30 fill-white/30'
            )}
          />
          {isRunning && (
            <Circle
              className="absolute inset-0 w-2 h-2 text-emerald-400 fill-emerald-400 animate-ping"
            />
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium text-white/80 truncate">
              {skill.display_name}
            </span>
          </div>
          {skill.description && (
            <p className="text-xs text-white/40 truncate mt-0.5">
              {skill.description}
            </p>
          )}
        </div>
      </div>

      {/* Hover action */}
      <button className="absolute top-2 right-2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-white/[0.06] transition-all">
        <ExternalLink className="w-3 h-3 text-white/40" />
      </button>
    </div>
  );
}
