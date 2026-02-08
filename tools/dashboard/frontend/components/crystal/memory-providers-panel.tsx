'use client';

import { useEffect, useState } from 'react';
import { Database, Star, AlertCircle, RefreshCw, HardDrive } from 'lucide-react';
import { CrystalCard, CrystalCardHeader, CrystalCardContent } from './crystal-card';
import { api, MemoryProvider } from '@/lib/api';
import { cn } from '@/lib/utils';

interface MemoryProvidersPanelProps {
  className?: string;
}

export function MemoryProvidersPanel({ className }: MemoryProvidersPanelProps) {
  const [providers, setProviders] = useState<MemoryProvider[]>([]);
  const [primaryProvider, setPrimaryProvider] = useState<string | undefined>();
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProviders = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getMemoryProviders();
      if (res.success && res.data) {
        setProviders(res.data.providers);
        setPrimaryProvider(res.data.primary_provider);
      } else {
        setError(res.error || 'Failed to load providers');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load providers');
    }
    setIsLoading(false);
  };

  useEffect(() => {
    fetchProviders();
  }, []);

  const activeCount = providers.filter((p) => p.status === 'active').length;

  return (
    <CrystalCard padding="none" className={className}>
      <div className="p-6">
        <CrystalCardHeader
          icon={<Database className="w-5 h-5" />}
          title="Memory Providers"
          subtitle={`${activeCount}/${providers.length} active`}
          action={
            <button
              onClick={fetchProviders}
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
          <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20">
            <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
            <span className="text-sm text-red-400">{error}</span>
          </div>
        ) : isLoading ? (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <div
                key={i}
                className="h-14 rounded-lg bg-white/[0.02] animate-pulse"
              />
            ))}
          </div>
        ) : providers.length === 0 ? (
          <div className="text-center py-6">
            <Database className="w-8 h-8 text-white/20 mx-auto mb-2" />
            <p className="text-sm text-white/40">No memory providers configured</p>
          </div>
        ) : (
          <div className="space-y-2">
            {providers.map((provider) => (
              <ProviderRow
                key={provider.name}
                provider={provider}
                isPrimary={provider.name === primaryProvider}
              />
            ))}
          </div>
        )}
      </CrystalCardContent>
    </CrystalCard>
  );
}

interface ProviderRowProps {
  provider: MemoryProvider;
  isPrimary: boolean;
}

function ProviderRow({ provider, isPrimary }: ProviderRowProps) {
  const statusColors = {
    active: 'text-emerald-400',
    inactive: 'text-white/40',
    error: 'text-red-400',
  };

  const statusBg = {
    active: 'bg-emerald-400',
    inactive: 'bg-white/20',
    error: 'bg-red-400',
  };

  return (
    <div
      className={cn(
        'flex items-center gap-3 p-3 rounded-lg transition-all duration-200',
        'border',
        isPrimary
          ? 'bg-white/[0.04] border-white/[0.08]'
          : 'bg-white/[0.02] border-white/[0.04]',
        'hover:bg-white/[0.05]'
      )}
    >
      {/* Primary indicator */}
      <div className="relative">
        {isPrimary ? (
          <div className="p-1.5 rounded-lg bg-amber-500/10">
            <Star className="w-4 h-4 text-amber-400 fill-amber-400" />
          </div>
        ) : (
          <div className="p-1.5 rounded-lg bg-white/[0.04]">
            <HardDrive className="w-4 h-4 text-white/40" />
          </div>
        )}
      </div>

      {/* Provider info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-white/80 capitalize">
            {provider.name}
          </span>
          {isPrimary && (
            <span className="px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-amber-500/10 text-amber-400">
              Primary
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <div
            className={cn('w-1.5 h-1.5 rounded-full', statusBg[provider.status])}
          />
          <span className={cn('text-xs capitalize', statusColors[provider.status])}>
            {provider.status}
          </span>
          {provider.error && (
            <span className="text-xs text-red-400 truncate">({provider.error})</span>
          )}
        </div>
      </div>

      {/* Storage info */}
      {provider.storage_used && (
        <div className="text-right">
          <div className="text-sm font-medium text-white/60">
            {provider.storage_used}
          </div>
          {provider.health_score !== undefined && (
            <div className="text-xs text-white/40">
              {Math.round(provider.health_score * 100)}% health
            </div>
          )}
        </div>
      )}
    </div>
  );
}
