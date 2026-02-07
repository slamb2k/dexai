'use client';

import { useState, useEffect } from 'react';
import {
  Search,
  Clock,
  Brain,
  History,
  RefreshCw,
  ChevronRight,
  AlertCircle,
  Database,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { CommitmentList, Commitment } from '@/components/commitment-badge';

interface ContextSnapshot {
  id: string;
  title: string;
  timestamp: Date;
  summary: string;
}

interface MemoryProvider {
  name: string;
  status: 'active' | 'inactive' | 'error';
  isPrimary: boolean;
  storageUsed?: string;
  healthScore?: number;
}

// Demo data
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

const demoSnapshots: ContextSnapshot[] = [
  {
    id: '1',
    title: 'Budget review for Q4',
    timestamp: new Date(Date.now() - 4 * 60 * 60 * 1000),
    summary: 'Reviewing quarterly projections with Sarah\'s team feedback',
  },
  {
    id: '2',
    title: 'Project planning session',
    timestamp: new Date(Date.now() - 24 * 60 * 60 * 1000),
    summary: 'Mapping out timeline for the new feature release',
  },
];

const demoProviders: MemoryProvider[] = [
  {
    name: 'Native',
    status: 'active',
    isPrimary: true,
    storageUsed: '2.4 GB',
    healthScore: 100,
  },
  {
    name: 'Mem0',
    status: 'active',
    isPrimary: false,
    storageUsed: '1.2 GB',
    healthScore: 98,
  },
  {
    name: 'Zep',
    status: 'inactive',
    isPrimary: false,
  },
];

export default function MemoryPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [commitments, setCommitments] = useState<Commitment[]>(demoCommitments);
  const [snapshots, setSnapshots] = useState<ContextSnapshot[]>(demoSnapshots);
  const [providers, setProviders] = useState<MemoryProvider[]>(demoProviders);
  const [searchResults, setSearchResults] = useState<{ id: string; content: string; score: number }[]>([]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsLoading(true);
    // Simulate search - in real implementation, call hybrid search API
    setTimeout(() => {
      setSearchResults([
        { id: '1', content: 'Meeting notes from last week about Q4 projections', score: 0.95 },
        { id: '2', content: 'Sarah mentioned needing the updated docs by Friday', score: 0.87 },
      ]);
      setIsLoading(false);
    }, 500);
  };

  const handleResumeContext = (snapshot: ContextSnapshot) => {
    // Navigate to home with context restored
    window.location.href = `/?resume=${snapshot.id}`;
  };

  const formatTimestamp = (date: Date) => {
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const days = Math.floor(hours / 24);

    if (hours < 1) return 'Just now';
    if (hours < 24) return `${hours}h ago`;
    if (days === 1) return 'Yesterday';
    return `${days} days ago`;
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
            {isLoading && <RefreshCw className="w-5 h-5 text-text-muted animate-spin" />}
          </div>
        </div>
      </form>

      {/* Search Results */}
      {searchResults.length > 0 && (
        <section>
          <h2 className="text-section-header text-text-primary mb-4">Search Results</h2>
          <div className="space-y-2">
            {searchResults.map((result) => (
              <div
                key={result.id}
                className="crystal-card p-4 hover:border-accent-primary/30 cursor-pointer transition-colors"
              >
                <p className="text-body text-text-primary">{result.content}</p>
                <p className="text-caption text-text-muted mt-1">
                  Relevance: {Math.round(result.score * 100)}%
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Waiting on You - RSD-Safe Language */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <Clock className="w-5 h-5 text-text-muted" />
          <h2 className="text-section-header text-text-primary">Waiting on you</h2>
        </div>
        <CommitmentList
          commitments={commitments}
          onSelect={(c) => {
            // Handle selecting a commitment
          }}
        />
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
                    <p className="text-caption text-text-muted mt-1 truncate">
                      {snapshot.summary}
                    </p>
                    <p className="text-caption text-text-disabled mt-2">
                      {formatTimestamp(snapshot.timestamp)}
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
                    {provider.isPrimary && (
                      <span className="badge badge-success text-xs">Primary</span>
                    )}
                  </div>
                  <p className="text-caption text-text-muted">
                    {provider.status === 'active'
                      ? `${provider.storageUsed} used`
                      : provider.status === 'error'
                      ? 'Connection error'
                      : 'Not configured'}
                  </p>
                </div>
              </div>
              {provider.healthScore !== undefined && (
                <div className="text-right">
                  <p className="text-body text-text-primary">{provider.healthScore}%</p>
                  <p className="text-caption text-text-muted">Health</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
