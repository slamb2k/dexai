'use client';

import { useEffect, useState } from 'react';
import { Building2, Cloud, Link2, CheckCircle2, XCircle, ExternalLink } from 'lucide-react';
import { CrystalCard, CrystalCardHeader, CrystalCardContent } from './crystal-card';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

interface OAuthStatusItem {
  provider: string;
  connected: boolean;
  email: string | null;
  integration_level: number | null;
}

interface OfficePanelProps {
  className?: string;
}

export function OfficePanel({ className }: OfficePanelProps) {
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
    <CrystalCard padding="none" className={className}>
      <div className="p-6">
        <CrystalCardHeader
          icon={<Building2 className="w-5 h-5" />}
          title="Office Integration"
          subtitle={`${connectedCount}/2 connected`}
        />
      </div>

      <CrystalCardContent className="px-6 pb-6 pt-0">
        <div className="grid grid-cols-2 gap-4">
          <OfficeProviderCard
            provider="microsoft"
            name="Microsoft 365"
            icon={<MicrosoftIcon />}
            status={microsoft}
            isLoading={isLoading}
          />
          <OfficeProviderCard
            provider="google"
            name="Google Workspace"
            icon={<GoogleIcon />}
            status={google}
            isLoading={isLoading}
          />
        </div>
      </CrystalCardContent>
    </CrystalCard>
  );
}

interface OfficeProviderCardProps {
  provider: 'microsoft' | 'google';
  name: string;
  icon: React.ReactNode;
  status: OAuthStatusItem | undefined;
  isLoading: boolean;
}

function OfficeProviderCard({
  provider,
  name,
  icon,
  status,
  isLoading,
}: OfficeProviderCardProps) {
  const isConnected = status?.connected ?? false;

  const handleConnect = async () => {
    try {
      const res = await api.getOAuthAuthorizationUrl(provider, 2);
      if (res.success && res.data?.authorization_url) {
        window.open(res.data.authorization_url, '_blank');
      }
    } catch (e) {
      console.error('Failed to get OAuth URL:', e);
    }
  };

  const levelLabels: Record<number, string> = {
    1: 'View Only',
    2: 'Read',
    3: 'Read/Draft',
    4: 'Send',
    5: 'Full Access',
  };

  return (
    <div
      className={cn(
        'relative p-4 rounded-xl transition-all duration-200',
        'border',
        isConnected
          ? 'bg-white/[0.03] border-white/[0.08]'
          : 'bg-white/[0.02] border-white/[0.04]'
      )}
    >
      {/* Provider icon and status */}
      <div className="flex items-start justify-between mb-3">
        <div
          className={cn(
            'p-2 rounded-lg',
            isConnected ? 'bg-white/[0.06]' : 'bg-white/[0.03]'
          )}
        >
          {icon}
        </div>
        <div
          className={cn(
            'flex items-center gap-1 px-2 py-0.5 rounded-full text-xs',
            isConnected
              ? 'bg-white/[0.06] text-white/60'
              : 'bg-white/[0.04] text-white/40'
          )}
        >
          {isConnected ? (
            <>
              <CheckCircle2 className="w-3 h-3" />
              <span>Connected</span>
            </>
          ) : (
            <>
              <XCircle className="w-3 h-3" />
              <span>Disconnected</span>
            </>
          )}
        </div>
      </div>

      {/* Name and details */}
      <div className="space-y-1">
        <h4 className="text-sm font-medium text-white/80">{name}</h4>
        {isConnected && status?.email && (
          <p className="text-xs text-white/40 truncate">{status.email}</p>
        )}
        {isConnected && status?.integration_level && (
          <p className="text-xs text-white/30">
            Level {status.integration_level}: {levelLabels[status.integration_level] || 'Custom'}
          </p>
        )}
      </div>

      {/* Action button */}
      {!isConnected && (
        <button
          onClick={handleConnect}
          disabled={isLoading}
          className={cn(
            'mt-3 w-full flex items-center justify-center gap-2',
            'px-3 py-2 rounded-lg text-xs font-medium',
            'bg-white/[0.04] border border-white/[0.06]',
            'hover:bg-white/[0.06] hover:border-white/[0.08]',
            'transition-all duration-200',
            isLoading && 'opacity-50 cursor-not-allowed'
          )}
        >
          <Link2 className="w-3.5 h-3.5" />
          Connect
        </button>
      )}

      {isConnected && (
        <button
          className={cn(
            'mt-3 w-full flex items-center justify-center gap-2',
            'px-3 py-2 rounded-lg text-xs',
            'text-white/40 hover:text-white/60',
            'transition-colors'
          )}
        >
          <ExternalLink className="w-3.5 h-3.5" />
          Manage
        </button>
      )}

      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/30 rounded-xl">
          <div className="w-5 h-5 border-2 border-white/20 border-t-white/60 rounded-full animate-spin" />
        </div>
      )}
    </div>
  );
}

// Microsoft icon - monochrome
function MicrosoftIcon() {
  return (
    <svg className="w-5 h-5 text-white/50" viewBox="0 0 23 23" fill="currentColor">
      <rect x="1" y="1" width="10" height="10" />
      <rect x="12" y="1" width="10" height="10" />
      <rect x="1" y="12" width="10" height="10" />
      <rect x="12" y="12" width="10" height="10" />
    </svg>
  );
}

// Google icon - monochrome
function GoogleIcon() {
  return (
    <svg className="w-5 h-5 text-white/50" viewBox="0 0 24 24" fill="currentColor">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  );
}
