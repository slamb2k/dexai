'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useToastStore } from '@/lib/store';
import { cn } from '@/lib/utils';
import {
  Building2,
  Mail,
  Calendar,
  Link2,
  ChevronRight,
  Shield,
  AlertTriangle,
  Check,
  Loader2,
  ExternalLink,
} from 'lucide-react';

// Types
interface OfficeAccount {
  id: string;
  provider: 'google' | 'microsoft';
  email_address: string;
  integration_level: number;
  integration_level_name: string;
  is_active: boolean;
  last_sync: string | null;
  created_at: string;
}

interface DraftSummary {
  pending: number;
  approved: number;
  sent: number;
}

interface MeetingSummary {
  proposed: number;
  confirmed: number;
}

// Integration level descriptions
const levelDescriptions: Record<number, { name: string; description: string; color: string }> = {
  1: {
    name: 'Sandboxed',
    description: 'Dex uses its own email. You forward content to share.',
    color: 'text-gray-400',
  },
  2: {
    name: 'Read-Only',
    description: 'Dex can read your inbox and calendar. Suggests actions only.',
    color: 'text-blue-400',
  },
  3: {
    name: 'Collaborative',
    description: 'Dex creates drafts and schedules meetings. You review before sending.',
    color: 'text-green-400',
  },
  4: {
    name: 'Managed Proxy',
    description: 'Dex sends on your behalf with undo window.',
    color: 'text-yellow-400',
  },
  5: {
    name: 'Autonomous',
    description: 'Dex manages email and calendar based on your policies.',
    color: 'text-purple-400',
  },
};

export default function OfficePage() {
  const [accounts, setAccounts] = useState<OfficeAccount[]>([]);
  const [draftSummary, setDraftSummary] = useState<DraftSummary>({ pending: 0, approved: 0, sent: 0 });
  const [meetingSummary, setMeetingSummary] = useState<MeetingSummary>({ proposed: 0, confirmed: 0 });
  const [isLoading, setIsLoading] = useState(true);
  const { addToast } = useToastStore();

  // Load data
  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      try {
        // Load accounts
        const accountsRes = await api.getOfficeAccounts();
        if (accountsRes.success && accountsRes.data) {
          setAccounts(accountsRes.data);

          // Load draft and meeting counts for each account
          let totalPending = 0;
          let totalProposed = 0;

          for (const account of accountsRes.data) {
            if (account.integration_level >= 3) {
              const draftsRes = await api.getOfficeDrafts(account.id);
              if (draftsRes.success && draftsRes.data) {
                totalPending += draftsRes.data.total;
              }

              const meetingsRes = await api.getOfficeMeetings(account.id);
              if (meetingsRes.success && meetingsRes.data) {
                totalProposed += meetingsRes.data.total;
              }
            }
          }

          setDraftSummary((prev) => ({ ...prev, pending: totalPending }));
          setMeetingSummary((prev) => ({ ...prev, proposed: totalProposed }));
        }
      } catch (error) {
        console.error('Failed to load office data:', error);
      }
      setIsLoading(false);
    };

    loadData();
  }, []);

  const handleConnect = async (provider: 'google' | 'microsoft') => {
    try {
      const res = await api.getOAuthAuthorizationUrl(provider, 3);
      if (res.success && res.data?.authorization_url) {
        window.location.href = res.data.authorization_url;
      } else {
        addToast({ type: 'error', message: 'Failed to get authorization URL' });
      }
    } catch (error) {
      addToast({ type: 'error', message: 'Failed to connect account' });
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-text-muted" size={32} />
      </div>
    );
  }

  return (
    <div className="space-y-8 pt-4 animate-fade-in">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <Building2 className="w-6 h-6 text-white/40" />
          <h1 className="text-2xl font-light tracking-wide text-white/90">Services</h1>
        </div>
        <p className="text-xs text-white/40 mt-1 tracking-wide">
          Manage email drafts and meeting schedules with ADHD-safe confirmation flows
        </p>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Drafts Card */}
        <Link href="/office/drafts" className="card p-6 hover:border-accent-primary transition-colors">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="p-3 rounded-full bg-accent-primary/10">
                <Mail className="text-accent-primary" size={24} />
              </div>
              <div>
                <h2 className="text-card-title text-text-primary">Email Drafts</h2>
                <p className="text-caption text-text-muted">Review and approve drafts before sending</p>
              </div>
            </div>
            <ChevronRight className="text-text-muted" size={20} />
          </div>
          {draftSummary.pending > 0 && (
            <div className="mt-4 flex items-center gap-2">
              <span className="badge badge-warning">{draftSummary.pending} pending</span>
            </div>
          )}
        </Link>

        {/* Meetings Card */}
        <Link href="/office/meetings" className="card p-6 hover:border-accent-primary transition-colors">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="p-3 rounded-full bg-accent-secondary/10">
                <Calendar className="text-accent-secondary" size={24} />
              </div>
              <div>
                <h2 className="text-card-title text-text-primary">Meetings</h2>
                <p className="text-caption text-text-muted">Schedule meetings with availability checking</p>
              </div>
            </div>
            <ChevronRight className="text-text-muted" size={20} />
          </div>
          {meetingSummary.proposed > 0 && (
            <div className="mt-4 flex items-center gap-2">
              <span className="badge badge-info">{meetingSummary.proposed} proposals</span>
            </div>
          )}
        </Link>
      </div>

      {/* Connected Accounts */}
      <div className="card">
        <div className="p-4 border-b border-border-default">
          <h2 className="text-section-header text-text-primary">Connected Accounts</h2>
        </div>

        {accounts.length === 0 ? (
          <div className="p-6 text-center">
            <Link2 className="mx-auto text-text-muted mb-3" size={32} />
            <p className="text-body text-text-secondary mb-4">No accounts connected yet</p>
            <div className="flex justify-center gap-3">
              <button onClick={() => handleConnect('google')} className="btn btn-primary">
                Connect Google
              </button>
              <button onClick={() => handleConnect('microsoft')} className="btn btn-secondary">
                Connect Microsoft
              </button>
            </div>
          </div>
        ) : (
          <div className="divide-y divide-border-default">
            {accounts.map((account) => (
              <AccountRow key={account.id} account={account} />
            ))}

            {/* Add another account */}
            <div className="p-4">
              <div className="flex gap-3">
                <button onClick={() => handleConnect('google')} className="btn btn-ghost text-caption">
                  + Add Google Account
                </button>
                <button onClick={() => handleConnect('microsoft')} className="btn btn-ghost text-caption">
                  + Add Microsoft Account
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Integration Levels Info */}
      <div className="card p-6">
        <h2 className="text-section-header text-text-primary mb-4">Integration Levels</h2>
        <div className="space-y-3">
          {[3, 4, 5].map((level) => {
            const info = levelDescriptions[level];
            return (
              <div key={level} className="flex items-start gap-3">
                <Shield className={cn('shrink-0 mt-0.5', info.color)} size={16} />
                <div>
                  <p className="text-body text-text-primary">
                    Level {level}: {info.name}
                  </p>
                  <p className="text-caption text-text-muted">{info.description}</p>
                </div>
              </div>
            );
          })}
        </div>
        <div className="mt-4 p-3 bg-accent-warning/10 rounded-lg">
          <div className="flex items-start gap-2">
            <AlertTriangle className="text-accent-warning shrink-0 mt-0.5" size={16} />
            <p className="text-caption text-text-secondary">
              <strong className="text-text-primary">ADHD-Safe:</strong> Level 3 (Collaborative) never sends
              emails automatically. You always review and approve before anything leaves your identity.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// Account row component
function AccountRow({ account }: { account: OfficeAccount }) {
  const levelInfo = levelDescriptions[account.integration_level];

  return (
    <div className="p-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        {/* Provider icon */}
        <div
          className={cn(
            'w-10 h-10 rounded-full flex items-center justify-center text-white font-bold',
            account.provider === 'google' ? 'bg-red-500' : 'bg-blue-500'
          )}
        >
          {account.provider === 'google' ? 'G' : 'M'}
        </div>

        {/* Account info */}
        <div>
          <p className="text-body text-text-primary">{account.email_address}</p>
          <div className="flex items-center gap-2 text-caption">
            <span className={levelInfo.color}>Level {account.integration_level}</span>
            <span className="text-text-muted">({levelInfo.name})</span>
            {account.is_active ? (
              <span className="flex items-center gap-1 text-accent-success">
                <Check size={12} />
                Active
              </span>
            ) : (
              <span className="flex items-center gap-1 text-accent-error">
                <AlertTriangle size={12} />
                Disconnected
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button className="btn btn-ghost text-caption">Settings</button>
      </div>
    </div>
  );
}
