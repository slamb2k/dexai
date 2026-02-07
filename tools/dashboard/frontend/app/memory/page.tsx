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
        <h1 className="text-page-title text-text-primary">Memory</h1>
        <p className="text-body text-text-secondary mt-1">
          Search your memories and track commitments
        </p>
      </div>

      {/* Error banner */}
      {error && !isDemo && (
        <div className="bg-status-error/10 border border-status-error/30 rounded-2xl px-4 py-3 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-status-error flex-shrink-0" />
          <p className="text-body text-status-error">{error}</p>
        </div>
      )}

      {/* Search */}
      <form onSubmit={handleSearch}>
        <div className="crystal-card p-2">
          <div className="flex items-center gap-3 px-4 py-2">
            <Search className="w-5 h-5 text-text-muted flex-shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search memories..."
              className="flex-1 bg-transparent text-body-lg text-text-primary placeholder:text-text-muted focus:outline-none"
            />
            {isSearching && <RefreshCw className="w-5 h-5 text-text-muted animate-spin" />}
          </div>
        </div>
      </form>

      {/* Search Results */}
      {searchResults.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-section-header text-text-primary">Search Results</h2>
            <button
              onClick={() => setSearchResults([])}
              className="text-caption text-text-muted hover:text-text-primary"
            >
              Clear
            </button>
          </div>
          <div className="space-y-2">
            {searchResults.map((result) => (
              <div
                key={result.id}
                className="crystal-card p-4 hover:border-accent-primary/30 cursor-pointer transition-colors"
              >
                <p className="text-body text-text-primary">{result.content}</p>
                <div className="flex items-center gap-4 mt-2">
                  <span className="text-caption text-text-muted">
                    Relevance: {Math.round(result.score * 100)}%
                  </span>
                  {result.entry_type && (
                    <span className="text-caption text-text-disabled">
                      {result.entry_type}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center justify-center p-8">
          <Loader2 className="w-6 h-6 text-text-muted animate-spin" />
        </div>
      )}

      {!isLoading && (
        <>
          {/* Waiting on You - RSD-Safe Language */}
          <section>
            <div className="flex items-center gap-2 mb-4">
              <Clock className="w-5 h-5 text-text-muted" />
              <h2 className="text-section-header text-text-primary">Waiting on you</h2>
              {commitments.length > 0 && (
                <span className="text-caption text-text-muted">({commitments.length})</span>
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
              <div className="crystal-card p-6 text-center">
                <p className="text-body text-text-muted">
                  No active commitments. Nice work!
                </p>
              </div>
            )}
          </section>

          {/* Context Snapshots */}
          <section>
            <div className="flex items-center gap-2 mb-4">
              <History className="w-5 h-5 text-text-muted" />
              <h2 className="text-section-header text-text-primary">Context Snapshots</h2>
            </div>
            <div className="space-y-2">
              {snapshots.length === 0 ? (
                <div className="crystal-card p-6 text-center">
                  <p className="text-body text-text-muted">No saved contexts yet</p>
                </div>
              ) : (
                snapshots.map((snapshot) => (
                  <button
                    key={snapshot.id}
                    onClick={() => handleResumeContext(snapshot)}
                    className="w-full crystal-card p-4 text-left group hover:border-accent-primary/30 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-body text-text-primary font-medium truncate">
                          {snapshot.title}
                        </p>
                        {snapshot.summary && (
                          <p className="text-caption text-text-muted mt-1 truncate">
                            {snapshot.summary}
                          </p>
                        )}
                        <p className="text-caption text-text-disabled mt-2">
                          {formatTimestamp(snapshot.created_at)}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 ml-4">
                        <span className="text-caption text-accent-primary opacity-0 group-hover:opacity-100 transition-opacity">
                          Resume
                        </span>
                        <ChevronRight className="w-4 h-4 text-text-muted group-hover:text-accent-primary transition-colors" />
                      </div>
                    </div>
                  </button>
                ))
              )}
            </div>
          </section>

          {/* Memory Providers */}
          <section>
            <div className="flex items-center gap-2 mb-4">
              <Database className="w-5 h-5 text-text-muted" />
              <h2 className="text-section-header text-text-primary">Memory Providers</h2>
            </div>
            <div className="crystal-card divide-y divide-border-default">
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
                          ? 'bg-status-success/20'
                          : provider.status === 'error'
                          ? 'bg-status-error/20'
                          : 'bg-bg-surface'
                      )}
                    >
                      {provider.status === 'active' ? (
                        <CheckCircle2 className="w-4 h-4 text-status-success" />
                      ) : provider.status === 'error' ? (
                        <XCircle className="w-4 h-4 text-status-error" />
                      ) : (
                        <Database className="w-4 h-4 text-text-muted" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-body text-text-primary font-medium">
                          {provider.name}
                        </p>
                        {provider.is_primary && (
                          <span className="badge badge-success text-xs">Primary</span>
                        )}
                      </div>
                      <p className="text-caption text-text-muted">
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
                      <p className="text-body text-text-primary">{provider.health_score}%</p>
                      <p className="text-caption text-text-muted">Health</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
