'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useToastStore } from '@/lib/store';
import { cn } from '@/lib/utils';
import {
  ArrowLeft,
  Mail,
  Send,
  Trash2,
  Edit2,
  AlertTriangle,
  Check,
  Loader2,
  RefreshCw,
  Clock,
  ChevronDown,
  X,
  AlertCircle,
} from 'lucide-react';

// Types
interface Draft {
  id: string;
  account_id: string;
  provider_draft_id: string | null;
  subject: string | null;
  recipients: string[];
  cc: string[] | null;
  bcc: string[] | null;
  body_text: string | null;
  body_preview: string | null;
  status: 'pending' | 'approved' | 'sent' | 'deleted';
  sentiment_score: number | null;
  sentiment_flags: string[] | null;
  created_at: string;
  updated_at: string;
}

interface Account {
  id: string;
  email_address: string;
  provider: string;
}

// Sentiment badge component
function SentimentBadge({ score, flags }: { score: number | null; flags: string[] | null }) {
  if (score === null) return null;

  const getColor = () => {
    if (score < 0.3) return 'bg-accent-success/20 text-accent-success';
    if (score < 0.5) return 'bg-accent-warning/20 text-accent-warning';
    return 'bg-accent-error/20 text-accent-error';
  };

  const getLabel = () => {
    if (score < 0.3) return 'Calm';
    if (score < 0.5) return 'Review';
    return 'High Emotion';
  };

  return (
    <div className="flex items-center gap-2">
      <span className={cn('badge', getColor())}>{getLabel()}</span>
      {flags && flags.length > 0 && (
        <span className="text-caption text-text-muted">({flags.slice(0, 2).join(', ')})</span>
      )}
    </div>
  );
}

// Draft card component
function DraftCard({
  draft,
  onApprove,
  onDelete,
  onView,
}: {
  draft: Draft;
  onApprove: () => void;
  onDelete: () => void;
  onView: () => void;
}) {
  const hasHighEmotion = (draft.sentiment_score ?? 0) >= 0.5;

  return (
    <div
      className={cn(
        'card p-4 hover:border-accent-primary transition-colors cursor-pointer',
        hasHighEmotion && 'border-accent-warning'
      )}
      onClick={onView}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-body text-text-primary truncate">
            {draft.subject || '(No subject)'}
          </h3>
          <p className="text-caption text-text-muted truncate">
            To: {draft.recipients.join(', ')}
          </p>
        </div>
        <SentimentBadge score={draft.sentiment_score} flags={draft.sentiment_flags} />
      </div>

      {/* Preview */}
      {draft.body_preview && (
        <p className="text-caption text-text-secondary line-clamp-2 mb-3">
          {draft.body_preview}
        </p>
      )}

      {/* High emotion warning */}
      {hasHighEmotion && (
        <div className="flex items-center gap-2 p-2 bg-accent-warning/10 rounded mb-3">
          <AlertTriangle className="text-accent-warning shrink-0" size={14} />
          <p className="text-caption text-accent-warning">
            This email has emotional content. Consider waiting before sending.
          </p>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between">
        <span className="text-caption text-text-muted">
          Created {new Date(draft.created_at).toLocaleDateString()}
        </span>

        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={onDelete}
            className="btn btn-ghost text-caption p-2 text-accent-error"
            title="Delete draft"
          >
            <Trash2 size={14} />
          </button>
          <button
            onClick={onApprove}
            className={cn(
              'btn btn-primary text-caption',
              hasHighEmotion && 'bg-accent-warning hover:bg-accent-warning/80'
            )}
          >
            <Check size={14} className="mr-1" />
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}

// Draft detail modal
function DraftDetailModal({
  draft,
  onClose,
  onApprove,
  onDelete,
}: {
  draft: Draft;
  onClose: () => void;
  onApprove: () => void;
  onDelete: () => void;
}) {
  const hasHighEmotion = (draft.sentiment_score ?? 0) >= 0.5;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-bg-surface border border-border-default rounded-card shadow-card w-full max-w-2xl max-h-[80vh] overflow-y-auto animate-scale-in">
        {/* Header */}
        <div className="sticky top-0 bg-bg-surface border-b border-border-default px-6 py-4 flex items-center justify-between">
          <h2 className="text-section-header text-text-primary">Draft Preview</h2>
          <button
            onClick={onClose}
            className="p-2 rounded-button hover:bg-bg-elevated transition-colors"
          >
            <X size={20} className="text-text-muted" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          {/* Sentiment warning */}
          {hasHighEmotion && (
            <div className="flex items-start gap-3 p-4 bg-accent-warning/10 border border-accent-warning/20 rounded-lg">
              <AlertTriangle className="text-accent-warning shrink-0 mt-0.5" size={20} />
              <div>
                <p className="text-body text-accent-warning font-medium">
                  High Emotional Content Detected
                </p>
                <p className="text-caption text-text-secondary mt-1">
                  This email may come across more strongly than intended. Consider waiting before
                  sending, or softening the tone.
                </p>
                {draft.sentiment_flags && draft.sentiment_flags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {draft.sentiment_flags.map((flag) => (
                      <span key={flag} className="badge bg-accent-warning/20 text-accent-warning">
                        {flag.replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Email details */}
          <div className="space-y-3">
            <div>
              <span className="text-caption text-text-muted">To:</span>
              <p className="text-body text-text-primary">{draft.recipients.join(', ')}</p>
            </div>

            {draft.cc && draft.cc.length > 0 && (
              <div>
                <span className="text-caption text-text-muted">CC:</span>
                <p className="text-body text-text-primary">{draft.cc.join(', ')}</p>
              </div>
            )}

            <div>
              <span className="text-caption text-text-muted">Subject:</span>
              <p className="text-body text-text-primary">{draft.subject || '(No subject)'}</p>
            </div>
          </div>

          {/* Body */}
          <div className="border-t border-border-default pt-4">
            <p className="text-body text-text-secondary whitespace-pre-wrap">
              {draft.body_text || '(No content)'}
            </p>
          </div>

          {/* Sentiment score */}
          {draft.sentiment_score !== null && (
            <div className="border-t border-border-default pt-4">
              <div className="flex items-center justify-between">
                <span className="text-caption text-text-muted">Sentiment Analysis</span>
                <SentimentBadge score={draft.sentiment_score} flags={draft.sentiment_flags} />
              </div>
              <div className="mt-2 h-2 bg-bg-elevated rounded-full overflow-hidden">
                <div
                  className={cn(
                    'h-full transition-all',
                    draft.sentiment_score < 0.3 && 'bg-accent-success',
                    draft.sentiment_score >= 0.3 && draft.sentiment_score < 0.5 && 'bg-accent-warning',
                    draft.sentiment_score >= 0.5 && 'bg-accent-error'
                  )}
                  style={{ width: `${draft.sentiment_score * 100}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-border-default px-6 py-4 flex items-center justify-between">
          <button onClick={onDelete} className="btn btn-ghost text-accent-error">
            <Trash2 size={14} className="mr-2" />
            Delete
          </button>
          <div className="flex items-center gap-3">
            <button onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button
              onClick={onApprove}
              className={cn(
                'btn btn-primary',
                hasHighEmotion && 'bg-accent-warning hover:bg-accent-warning/80'
              )}
            >
              <Check size={14} className="mr-2" />
              {hasHighEmotion ? 'Approve Anyway' : 'Approve Draft'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function DraftsPage() {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [selectedDraft, setSelectedDraft] = useState<Draft | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const { addToast } = useToastStore();

  // Load accounts and drafts
  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const accountsRes = await api.getOfficeAccounts();
      if (accountsRes.success && accountsRes.data) {
        const level3Accounts = accountsRes.data.filter((a: any) => a.integration_level >= 3);
        setAccounts(level3Accounts);

        if (level3Accounts.length > 0 && !selectedAccount) {
          setSelectedAccount(level3Accounts[0].id);
        }
      }
    } catch (error) {
      console.error('Failed to load accounts:', error);
    }
    setIsLoading(false);
  }, [selectedAccount]);

  // Load drafts for selected account
  const loadDrafts = useCallback(async () => {
    if (!selectedAccount) return;

    try {
      const res = await api.getOfficeDrafts(selectedAccount);
      if (res.success && res.data) {
        setDrafts(res.data.drafts);
      }
    } catch (error) {
      console.error('Failed to load drafts:', error);
    }
  }, [selectedAccount]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (selectedAccount) {
      loadDrafts();
    }
  }, [selectedAccount, loadDrafts]);

  const handleApprove = async (draftId: string) => {
    try {
      const res = await api.approveOfficeDraft(draftId);
      if (res.success) {
        addToast({ type: 'success', message: 'Draft approved! You can now send it from your email client.' });
        setSelectedDraft(null);
        loadDrafts();
      } else {
        addToast({ type: 'error', message: res.error || 'Failed to approve draft' });
      }
    } catch (error) {
      addToast({ type: 'error', message: 'Failed to approve draft' });
    }
  };

  const handleDelete = async (draftId: string) => {
    try {
      const res = await api.deleteOfficeDraft(draftId);
      if (res.success) {
        addToast({ type: 'info', message: 'Draft deleted' });
        setSelectedDraft(null);
        loadDrafts();
      } else {
        addToast({ type: 'error', message: res.error || 'Failed to delete draft' });
      }
    } catch (error) {
      addToast({ type: 'error', message: 'Failed to delete draft' });
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
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link href="/office" className="btn btn-ghost p-2">
          <ArrowLeft size={20} />
        </Link>
        <div>
          <h1 className="text-page-title text-text-primary">Email Drafts</h1>
          <p className="text-body text-text-secondary">
            Review and approve drafts before they can be sent
          </p>
        </div>
      </div>

      {/* Account selector */}
      {accounts.length > 1 && (
        <div className="flex items-center gap-3">
          <span className="text-caption text-text-muted">Account:</span>
          <div className="relative">
            <select
              value={selectedAccount}
              onChange={(e) => setSelectedAccount(e.target.value)}
              className="input pr-8 appearance-none cursor-pointer"
            >
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.email_address}
                </option>
              ))}
            </select>
            <ChevronDown
              size={16}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
            />
          </div>
          <button onClick={loadDrafts} className="btn btn-ghost p-2">
            <RefreshCw size={16} />
          </button>
        </div>
      )}

      {/* No accounts warning */}
      {accounts.length === 0 && (
        <div className="card p-6 text-center">
          <AlertCircle className="mx-auto text-text-muted mb-3" size={32} />
          <p className="text-body text-text-secondary mb-4">
            No accounts with Level 3+ integration. Drafts require Collaborative level or higher.
          </p>
          <Link href="/office" className="btn btn-primary">
            Connect Account
          </Link>
        </div>
      )}

      {/* Drafts list */}
      {accounts.length > 0 && (
        <>
          <p className="text-caption text-text-muted">
            {drafts.length} pending draft{drafts.length !== 1 ? 's' : ''}
          </p>

          {drafts.length === 0 ? (
            <div className="card p-6 text-center">
              <Mail className="mx-auto text-text-muted mb-3" size={32} />
              <p className="text-body text-text-secondary">No pending drafts</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {drafts.map((draft) => (
                <DraftCard
                  key={draft.id}
                  draft={draft}
                  onApprove={() => handleApprove(draft.id)}
                  onDelete={() => handleDelete(draft.id)}
                  onView={() => setSelectedDraft(draft)}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Detail modal */}
      {selectedDraft && (
        <DraftDetailModal
          draft={selectedDraft}
          onClose={() => setSelectedDraft(null)}
          onApprove={() => handleApprove(selectedDraft.id)}
          onDelete={() => handleDelete(selectedDraft.id)}
        />
      )}
    </div>
  );
}
