'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Search,
  Clock,
  History,
  RefreshCw,
  ChevronRight,
  Database,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { CommitmentList, Commitment } from '@/components/commitment-badge';
import { CrystalCard, CrystalCardHeader, CrystalCardContent } from '@/components/crystal';
import { api, MemorySearchResult, MemoryContext, MemoryProvider, MemoryCommitment } from '@/lib/api';

const isDemo = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

// Demo data (fallback)
const demoCommitments: Commitment[] = [
  {
    id: '1',
    personName: 'Sarah',
    description: 'Q4 docs',
    createdAt: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000),
  },
  {
    id: '2',
    personName: 'Mike',
    description: 'callback about project timeline',
    createdAt: new Date(),
  },
];

const demoSnapshots: MemoryContext[] = [
  {
    id: '1',
    title: 'Budget review for Q4',
    created_at: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
    summary: 'Reviewing quarterly projections with Sarah\'s team feedback',
  },
  {
    id: '2',
    title: 'Project planning session',
    created_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    summary: 'Mapping out timeline for the new feature release',
  },
];

const demoProviders: MemoryProvider[] = [
  {
    name: 'Native',
    status: 'active',
    is_primary: true,
    storage_used: '2.4 GB',
    health_score: 100,
  },
  {
    name: 'Mem0',
    status: 'active',
    is_primary: false,
    storage_used: '1.2 GB',
    health_score: 98,
  },
  {
    name: 'Zep',
    status: 'inactive',
    is_primary: false,
  },
];

export default function MemoryPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [commitments, setCommitments] = useState<Commitment[]>([]);
  const [snapshots, setSnapshots] = useState<MemoryContext[]>([]);
  const [providers, setProviders] = useState<MemoryProvider[]>([]);
  const [searchResults, setSearchResults] = useState<MemorySearchResult[]>([]);

  // Load initial data
  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Load commitments
      const commitmentsRes = await api.getCommitments('active', 20);
      if (commitmentsRes.success && commitmentsRes.data) {
        setCommitments(
          commitmentsRes.data.commitments.map((c: MemoryCommitment) => ({
            id: c.id,
            personName: c.target_person || 'Someone',
            description: c.content,
            createdAt: new Date(c.created_at),
            dueDate: c.due_date ? new Date(c.due_date) : undefined,
          }))
        );
      } else if (isDemo) {
        setCommitments(demoCommitments);
      }

      // Load context snapshots
      const contextsRes = await api.getContextSnapshots(10);
      if (contextsRes.success && contextsRes.data) {
        setSnapshots(contextsRes.data.contexts);
      } else if (isDemo) {
        setSnapshots(demoSnapshots);
      }

      // Load providers
      const providersRes = await api.getMemoryProviders();
      if (providersRes.success && providersRes.data) {
        setProviders(providersRes.data.providers);
      } else if (isDemo) {
        setProviders(demoProviders);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load data');
      if (isDemo) {
        setCommitments(demoCommitments);
        setSnapshots(demoSnapshots);
        setProviders(demoProviders);
      }
    }

    setIsLoading(false);
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    setError(null);

    try {
      const res = await api.searchMemory(searchQuery, 10);
      if (res.success && res.data) {
        setSearchResults(res.data.results);
      } else if (isDemo) {
        // Demo fallback
        setSearchResults([
          { id: '1', content: 'Meeting notes from last week about Q4 projections', score: 0.95 },
          { id: '2', content: 'Sarah mentioned needing the updated docs by Friday', score: 0.87 },
        ]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Search failed');
      if (isDemo) {
        setSearchResults([
          { id: '1', content: 'Meeting notes from last week about Q4 projections', score: 0.95 },
          { id: '2', content: 'Sarah mentioned needing the updated docs by Friday', score: 0.87 },
        ]);
      }
    }

    setIsSearching(false);
  };

  const handleResumeContext = async (context: MemoryContext) => {
    try {
      const res = await api.restoreContext(context.id);
      if (res.success) {
        // Navigate to home with context restored
        window.location.href = `/?resume=${context.id}`;
      }
    } catch (e) {
      console.error('Failed to restore context:', e);
      // Fallback: just navigate
      window.location.href = `/?resume=${context.id}`;
    }
  };

  const formatTimestamp = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diff = now.getTime() - date.getTime();
      const hours = Math.floor(diff / (1000 * 60 * 60));
      const days = Math.floor(hours / 24);

      if (hours < 1) return 'Just now';
      if (hours < 24) return `${hours}h ago`;
      if (days === 1) return 'Yesterday';
      return `${days} days ago`;
    } catch {
      return 'Unknown';
    }
  };

  return (
    <div className="space-y-8 animate-fade-in max-w-4xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-light tracking-wide text-white/90">Memory</h1>
        <p className="text-sm text-white/60 mt-1">
          Search your memories and track commitments
        </p>
      </div>

      {/* Error banner */}
      {error && !isDemo && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-2xl px-4 py-3 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {/* Search */}
      <form onSubmit={handleSearch}>
        <CrystalCard padding="sm">
          <div className="flex items-center gap-3 px-2 py-1">
            <Search className="w-5 h-5 text-white/40 flex-shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search memories..."
              className="flex-1 bg-transparent text-base text-white/90 placeholder:text-white/40 focus:outline-none"
            />
            {isSearching && <RefreshCw className="w-5 h-5 text-white/40 animate-spin" />}
          </div>
        </CrystalCard>
      </form>

      {/* Search Results */}
      {searchResults.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-medium text-white/90">Search Results</h2>
            <button
              onClick={() => setSearchResults([])}
              className="text-xs text-white/40 hover:text-white/90 transition-colors"
            >
              Clear
            </button>
          </div>
          <div className="space-y-2">
            {searchResults.map((result) => (
              <CrystalCard
                key={result.id}
                padding="md"
                hover
                className="cursor-pointer"
              >
                <p className="text-sm text-white/90">{result.content}</p>
                <div className="flex items-center gap-4 mt-2">
                  <span className="text-xs text-white/40">
                    Relevance: {Math.round(result.score * 100)}%
                  </span>
                  {result.entry_type && (
                    <span className="text-xs text-white/20">
                      {result.entry_type}
                    </span>
                  )}
                </div>
              </CrystalCard>
            ))}
          </div>
        </section>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center justify-center p-8">
          <Loader2 className="w-6 h-6 text-white/40 animate-spin" />
        </div>
      )}

      {!isLoading && (
        <>
          {/* Waiting on You - RSD-Safe Language */}
          <section>
            <div className="flex items-center gap-2 mb-4">
              <Clock className="w-5 h-5 text-white/40" />
              <h2 className="text-lg font-medium text-white/90">Waiting on you</h2>
              {commitments.length > 0 && (
                <span className="text-xs text-white/40">({commitments.length})</span>
              )}
            </div>
            {commitments.length > 0 ? (
              <CommitmentList
                commitments={commitments}
                onSelect={(c) => {
                  // Could show commitment details or mark as resolved
                  console.log('Selected commitment:', c);
                }}
              />
            ) : (
              <CrystalCard padding="lg" className="text-center">
                <p className="text-sm text-white/40">
                  No active commitments. Nice work!
                </p>
              </CrystalCard>
            )}
          </section>

          {/* Context Snapshots */}
          <section>
            <div className="flex items-center gap-2 mb-4">
              <History className="w-5 h-5 text-white/40" />
              <h2 className="text-lg font-medium text-white/90">Context Snapshots</h2>
            </div>
            <div className="space-y-2">
              {snapshots.length === 0 ? (
                <CrystalCard padding="lg" className="text-center">
                  <p className="text-sm text-white/40">No saved contexts yet</p>
                </CrystalCard>
              ) : (
                snapshots.map((snapshot) => (
                  <button
                    key={snapshot.id}
                    onClick={() => handleResumeContext(snapshot)}
                    className="w-full text-left group"
                  >
                    <CrystalCard padding="md" hover>
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-white/90 font-medium truncate">
                            {snapshot.title}
                          </p>
                          {snapshot.summary && (
                            <p className="text-xs text-white/40 mt-1 truncate">
                              {snapshot.summary}
                            </p>
                          )}
                          <p className="text-xs text-white/20 mt-2">
                            {formatTimestamp(snapshot.created_at)}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 ml-4">
                          <span className="text-xs text-emerald-400 opacity-0 group-hover:opacity-100 transition-opacity">
                            Resume
                          </span>
                          <ChevronRight className="w-4 h-4 text-white/40 group-hover:text-emerald-400 transition-colors" />
                        </div>
                      </div>
                    </CrystalCard>
                  </button>
                ))
              )}
            </div>
          </section>

          {/* Memory Providers */}
          <section>
            <div className="flex items-center gap-2 mb-4">
              <Database className="w-5 h-5 text-white/40" />
              <h2 className="text-lg font-medium text-white/90">Memory Providers</h2>
            </div>
            <CrystalCard padding="none" className="divide-y divide-white/[0.06]">
              {providers.map((provider) => (
                <div
                  key={provider.name}
                  className="p-4 flex items-center justify-between"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        'w-8 h-8 rounded-lg flex items-center justify-center',
                        provider.status === 'active'
                          ? 'bg-emerald-500/20'
                          : provider.status === 'error'
                          ? 'bg-red-500/20'
                          : 'bg-white/[0.04]'
                      )}
                    >
                      {provider.status === 'active' ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      ) : provider.status === 'error' ? (
                        <XCircle className="w-4 h-4 text-red-400" />
                      ) : (
                        <Database className="w-4 h-4 text-white/40" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-sm text-white/90 font-medium">
                          {provider.name}
                        </p>
                        {provider.is_primary && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400">
                            Primary
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-white/40">
                        {provider.status === 'active'
                          ? provider.storage_used || 'Connected'
                          : provider.status === 'error'
                          ? provider.error || 'Connection error'
                          : 'Not configured'}
                      </p>
                    </div>
                  </div>
                  {provider.health_score !== undefined && (
                    <div className="text-right">
                      <p className="text-sm text-white/90">{provider.health_score}%</p>
                      <p className="text-xs text-white/40">Health</p>
                    </div>
                  )}
                </div>
              ))}
            </CrystalCard>
          </section>
        </>
      )}
    </div>
  );
}
