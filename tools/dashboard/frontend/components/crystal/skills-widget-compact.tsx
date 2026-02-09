'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Sparkles, ChevronRight } from 'lucide-react';
import { api, SkillsSummary } from '@/lib/api';
import { cn } from '@/lib/utils';

interface SkillsWidgetCompactProps {
  className?: string;
}

export function SkillsWidgetCompact({ className }: SkillsWidgetCompactProps) {
  const [summary, setSummary] = useState<SkillsSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchSummary = async () => {
      try {
        const res = await api.getSkillsSummary();
        if (res.success && res.data) {
          setSummary(res.data);
        }
      } catch (e) {
        console.error('Failed to fetch skills summary:', e);
      }
      setIsLoading(false);
    };

    fetchSummary();
  }, []);

  return (
    <Link href="/skills" className={cn('block group', className)}>
      <div
        className={cn(
          'flex items-center justify-between p-3 rounded-xl',
          'bg-white/[0.02] border border-white/[0.06]',
          'hover:bg-white/[0.04] hover:border-white/[0.08]',
          'transition-all duration-200',
          isLoading && 'animate-pulse'
        )}
      >
        <div className="flex items-center gap-3">
          {/* Skills Icon */}
          <div className="p-2 rounded-lg bg-white/[0.04] border border-white/[0.06]">
            <Sparkles className="w-4 h-4 text-white/50" />
          </div>

          {/* Labels */}
          <div>
            <p className="text-sm font-medium text-white/80">Skills</p>
            <div className="flex items-center gap-2 mt-0.5">
              {summary ? (
                <>
                  {/* Built-in count */}
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-violet-500/10 text-violet-400 border border-violet-500/20">
                    {summary.builtin} built-in
                  </span>
                  {/* User count */}
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-teal-500/10 text-teal-400 border border-teal-500/20">
                    {summary.user} user
                  </span>
                </>
              ) : (
                <span className="text-xs text-white/40">Loading...</span>
              )}
            </div>
          </div>
        </div>

        {/* Arrow indicator */}
        <ChevronRight className="w-4 h-4 text-white/30 group-hover:text-white/50 transition-colors" />
      </div>
    </Link>
  );
}
