'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Building2, ChevronRight } from 'lucide-react';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

interface OAuthStatusItem {
  provider: string;
  connected: boolean;
  email: string | null;
  integration_level: number | null;
}

interface ServicesWidgetCompactProps {
  className?: string;
}

export function ServicesWidgetCompact({ className }: ServicesWidgetCompactProps) {
  const [oauthStatus, setOauthStatus] = useState<OAuthStatusItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await api.getOAuthStatus();
        if (res.success && res.data) {
          setOauthStatus(res.data);
        }
      } catch (e) {
        console.error('Failed to fetch OAuth status:', e);
      }
      setIsLoading(false);
    };

    fetchStatus();
  }, []);

  const microsoft = oauthStatus.find((s) => s.provider === 'microsoft');
  const google = oauthStatus.find((s) => s.provider === 'google');
  const connectedCount = oauthStatus.filter((s) => s.connected).length;

  return (
    <Link href="/office" className={cn('block group', className)}>
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
          {/* Services Icon */}
          <div className="p-2 rounded-lg bg-white/[0.04] border border-white/[0.06]">
            <Building2 className="w-4 h-4 text-white/50" />
          </div>

          {/* Labels */}
          <div>
            <p className="text-sm font-medium text-white/80">Services</p>
            <div className="flex items-center gap-2 mt-0.5">
              {/* Microsoft status dot */}
              <div className="flex items-center gap-1">
                <div
                  className={cn(
                    'w-1.5 h-1.5 rounded-full',
                    microsoft?.connected ? 'bg-emerald-400' : 'bg-white/20'
                  )}
                />
                <span className="text-xs text-white/40">MS</span>
              </div>

              {/* Google status dot */}
              <div className="flex items-center gap-1">
                <div
                  className={cn(
                    'w-1.5 h-1.5 rounded-full',
                    google?.connected ? 'bg-emerald-400' : 'bg-white/20'
                  )}
                />
                <span className="text-xs text-white/40">Google</span>
              </div>

              <span className="text-xs text-white/30 ml-1">
                {connectedCount}/2
              </span>
            </div>
          </div>
        </div>

        {/* Arrow indicator */}
        <ChevronRight className="w-4 h-4 text-white/30 group-hover:text-white/50 transition-colors" />
      </div>
    </Link>
  );
}
