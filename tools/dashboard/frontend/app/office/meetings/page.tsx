'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useToastStore } from '@/lib/store';
import { cn, formatDate, formatTimestamp } from '@/lib/utils';
import {
  ArrowLeft,
  Calendar,
  Clock,
  MapPin,
  Users,
  Check,
  X,
  Loader2,
  RefreshCw,
  ChevronDown,
  AlertCircle,
  AlertTriangle,
  Sparkles,
} from 'lucide-react';

// Types
interface MeetingProposal {
  id: string;
  account_id: string;
  provider_event_id: string | null;
  title: string;
  description: string | null;
  location: string | null;
  start_time: string;
  end_time: string;
  timezone: string | null;
  attendees: string[] | null;
  organizer_email: string | null;
  status: 'proposed' | 'confirmed' | 'cancelled';
  conflicts: ConflictInfo[] | null;
  created_at: string;
}

interface ConflictInfo {
  event_id: string;
  title: string;
  start_time: string;
  end_time: string;
}

interface TimeSuggestion {
  start: string;
  end: string;
  score: number;
  reason: string;
}

interface Account {
  id: string;
  email_address: string;
  provider: string;
}

// Conflict warning component
function ConflictWarning({ conflicts }: { conflicts: ConflictInfo[] }) {
  if (!conflicts || conflicts.length === 0) return null;

  return (
    <div className="flex items-start gap-2 p-2 bg-accent-warning/10 rounded">
      <AlertTriangle className="text-accent-warning shrink-0 mt-0.5" size={14} />
      <div>
        <p className="text-caption text-accent-warning font-medium">
          {conflicts.length} conflict{conflicts.length !== 1 ? 's' : ''}
        </p>
        <ul className="text-caption text-text-muted mt-1">
          {conflicts.slice(0, 2).map((c, i) => (
            <li key={i}>
              {c.title} ({new Date(c.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

// Attendee list component
function AttendeeList({ attendees }: { attendees: string[] | null }) {
  if (!attendees || attendees.length === 0) return null;

  return (
    <div className="flex items-start gap-2">
      <Users className="text-text-muted shrink-0 mt-0.5" size={14} />
      <div className="text-caption text-text-secondary">
        {attendees.slice(0, 3).map((email, i) => (
          <span key={email}>
            {email}
            {i < Math.min(attendees.length, 3) - 1 && ', '}
          </span>
        ))}
        {attendees.length > 3 && (
          <span className="text-text-muted"> +{attendees.length - 3} more</span>
        )}
      </div>
    </div>
  );
}

// Meeting card component
function MeetingCard({
  meeting,
  onConfirm,
  onCancel,
  onView,
}: {
  meeting: MeetingProposal;
  onConfirm: () => void;
  onCancel: () => void;
  onView: () => void;
}) {
  const startDate = new Date(meeting.start_time);
  const endDate = new Date(meeting.end_time);
  const hasConflicts = meeting.conflicts && meeting.conflicts.length > 0;

  return (
    <div
      className={cn(
        'card p-4 hover:border-accent-primary transition-colors cursor-pointer',
        hasConflicts && 'border-accent-warning'
      )}
      onClick={onView}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <h3 className="text-body text-text-primary">{meeting.title}</h3>
        {meeting.status === 'confirmed' && (
          <span className="badge badge-success">Confirmed</span>
        )}
      </div>

      {/* Time */}
      <div className="flex items-center gap-2 text-caption text-text-secondary mb-2">
        <Clock size={14} />
        <span>
          {formatDate(startDate)} {formatTimestamp(startDate)} - {formatTimestamp(endDate)}
        </span>
      </div>

      {/* Location */}
      {meeting.location && (
        <div className="flex items-center gap-2 text-caption text-text-secondary mb-2">
          <MapPin size={14} />
          <span>{meeting.location}</span>
        </div>
      )}

      {/* Attendees */}
      <AttendeeList attendees={meeting.attendees} />

      {/* Conflicts */}
      {hasConflicts && (
        <div className="mt-3">
          <ConflictWarning conflicts={meeting.conflicts!} />
        </div>
      )}

      {/* Actions */}
      {meeting.status === 'proposed' && (
        <div className="flex items-center justify-end gap-2 mt-4" onClick={(e) => e.stopPropagation()}>
          <button onClick={onCancel} className="btn btn-ghost text-caption p-2 text-accent-error">
            <X size={14} />
          </button>
          <button
            onClick={onConfirm}
            className={cn(
              'btn btn-primary text-caption',
              hasConflicts && 'bg-accent-warning hover:bg-accent-warning/80'
            )}
          >
            <Check size={14} className="mr-1" />
            Confirm
          </button>
        </div>
      )}
    </div>
  );
}

// Meeting detail modal
function MeetingDetailModal({
  meeting,
  onClose,
  onConfirm,
  onCancel,
}: {
  meeting: MeetingProposal;
  onClose: () => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const startDate = new Date(meeting.start_time);
  const endDate = new Date(meeting.end_time);
  const hasConflicts = meeting.conflicts && meeting.conflicts.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      <div className="relative bg-bg-surface border border-border-default rounded-card shadow-card w-full max-w-2xl max-h-[80vh] overflow-y-auto animate-scale-in">
        {/* Header */}
        <div className="sticky top-0 bg-bg-surface border-b border-border-default px-6 py-4 flex items-center justify-between">
          <h2 className="text-section-header text-text-primary">Meeting Details</h2>
          <button
            onClick={onClose}
            className="p-2 rounded-button hover:bg-bg-elevated transition-colors"
          >
            <X size={20} className="text-text-muted" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          {/* Conflict warning */}
          {hasConflicts && (
            <div className="flex items-start gap-3 p-4 bg-accent-warning/10 border border-accent-warning/20 rounded-lg">
              <AlertTriangle className="text-accent-warning shrink-0 mt-0.5" size={20} />
              <div>
                <p className="text-body text-accent-warning font-medium">
                  Calendar Conflicts Detected
                </p>
                <ul className="text-caption text-text-secondary mt-2 space-y-1">
                  {meeting.conflicts!.map((conflict, i) => (
                    <li key={i}>
                      {conflict.title} at{' '}
                      {new Date(conflict.start_time).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Title */}
          <div>
            <h3 className="text-card-title text-text-primary">{meeting.title}</h3>
            {meeting.description && (
              <p className="text-body text-text-secondary mt-1">{meeting.description}</p>
            )}
          </div>

          {/* Time */}
          <div className="flex items-center gap-3">
            <Calendar className="text-text-muted" size={20} />
            <div>
              <p className="text-body text-text-primary">{formatDate(startDate)}</p>
              <p className="text-caption text-text-secondary">
                {formatTimestamp(startDate)} - {formatTimestamp(endDate)}
              </p>
            </div>
          </div>

          {/* Location */}
          {meeting.location && (
            <div className="flex items-center gap-3">
              <MapPin className="text-text-muted" size={20} />
              <p className="text-body text-text-primary">{meeting.location}</p>
            </div>
          )}

          {/* Attendees */}
          {meeting.attendees && meeting.attendees.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Users className="text-text-muted" size={20} />
                <span className="text-caption text-text-muted">
                  {meeting.attendees.length} attendee{meeting.attendees.length !== 1 ? 's' : ''}
                </span>
              </div>
              <div className="space-y-1 ml-7">
                {meeting.attendees.map((email) => (
                  <p key={email} className="text-body text-text-secondary">
                    {email}
                  </p>
                ))}
              </div>
            </div>
          )}

          {/* Info box */}
          <div className="p-3 bg-bg-elevated rounded-lg">
            <p className="text-caption text-text-muted">
              Confirming this meeting will create a calendar event and send invitations to all
              attendees.
            </p>
          </div>
        </div>

        {/* Footer */}
        {meeting.status === 'proposed' && (
          <div className="border-t border-border-default px-6 py-4 flex items-center justify-between">
            <button onClick={onCancel} className="btn btn-ghost text-accent-error">
              Cancel Proposal
            </button>
            <div className="flex items-center gap-3">
              <button onClick={onClose} className="btn btn-secondary">
                Close
              </button>
              <button
                onClick={onConfirm}
                className={cn(
                  'btn btn-primary',
                  hasConflicts && 'bg-accent-warning hover:bg-accent-warning/80'
                )}
              >
                <Check size={14} className="mr-2" />
                {hasConflicts ? 'Confirm Anyway' : 'Confirm Meeting'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Time suggestions component
function TimeSuggestions({
  accountId,
  onSelect,
}: {
  accountId: string;
  onSelect: (suggestion: TimeSuggestion) => void;
}) {
  const [suggestions, setSuggestions] = useState<TimeSuggestion[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const loadSuggestions = async () => {
    setIsLoading(true);
    try {
      const res = await api.getOfficeMeetingSuggestions(accountId, 30, 7);
      if (res.success && res.data) {
        setSuggestions(res.data);
      }
    } catch (error) {
      console.error('Failed to load suggestions:', error);
    }
    setIsLoading(false);
  };

  useEffect(() => {
    if (accountId) {
      loadSuggestions();
    }
  }, [accountId]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 className="animate-spin text-text-muted" size={20} />
      </div>
    );
  }

  if (suggestions.length === 0) {
    return null;
  }

  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles className="text-accent-primary" size={16} />
        <h3 className="text-card-title text-text-primary">Suggested Times</h3>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {suggestions.slice(0, 4).map((suggestion, i) => {
          const start = new Date(suggestion.start);
          return (
            <button
              key={i}
              onClick={() => onSelect(suggestion)}
              className="flex items-center justify-between p-3 bg-bg-elevated hover:bg-bg-input rounded transition-colors text-left"
            >
              <div>
                <p className="text-body text-text-primary">
                  {start.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
                </p>
                <p className="text-caption text-text-muted">
                  {start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>
              <div className="text-right">
                <span className="text-caption text-accent-primary">{suggestion.reason}</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState<MeetingProposal[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [selectedMeeting, setSelectedMeeting] = useState<MeetingProposal | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const { addToast } = useToastStore();

  // Load accounts
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

  // Load meetings for selected account
  const loadMeetings = useCallback(async () => {
    if (!selectedAccount) return;

    try {
      const res = await api.getOfficeMeetings(selectedAccount);
      if (res.success && res.data) {
        setMeetings(res.data.proposals);
      }
    } catch (error) {
      console.error('Failed to load meetings:', error);
    }
  }, [selectedAccount]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (selectedAccount) {
      loadMeetings();
    }
  }, [selectedAccount, loadMeetings]);

  const handleConfirm = async (proposalId: string) => {
    try {
      const res = await api.confirmOfficeMeeting(proposalId);
      if (res.success) {
        addToast({ type: 'success', message: 'Meeting confirmed! Invites sent to attendees.' });
        setSelectedMeeting(null);
        loadMeetings();
      } else {
        addToast({ type: 'error', message: res.error || 'Failed to confirm meeting' });
      }
    } catch (error) {
      addToast({ type: 'error', message: 'Failed to confirm meeting' });
    }
  };

  const handleCancel = async (proposalId: string) => {
    try {
      const res = await api.cancelOfficeMeeting(proposalId);
      if (res.success) {
        addToast({ type: 'info', message: 'Meeting proposal cancelled' });
        setSelectedMeeting(null);
        loadMeetings();
      } else {
        addToast({ type: 'error', message: res.error || 'Failed to cancel meeting' });
      }
    } catch (error) {
      addToast({ type: 'error', message: 'Failed to cancel meeting' });
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
          <h1 className="text-page-title text-text-primary">Meetings</h1>
          <p className="text-body text-text-secondary">
            Schedule and confirm meetings with availability checking
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
          <button onClick={loadMeetings} className="btn btn-ghost p-2">
            <RefreshCw size={16} />
          </button>
        </div>
      )}

      {/* No accounts warning */}
      {accounts.length === 0 && (
        <div className="card p-6 text-center">
          <AlertCircle className="mx-auto text-text-muted mb-3" size={32} />
          <p className="text-body text-text-secondary mb-4">
            No accounts with Level 3+ integration. Meeting scheduling requires Collaborative level
            or higher.
          </p>
          <Link href="/office" className="btn btn-primary">
            Connect Account
          </Link>
        </div>
      )}

      {/* Time suggestions */}
      {selectedAccount && <TimeSuggestions accountId={selectedAccount} onSelect={() => {}} />}

      {/* Meetings list */}
      {accounts.length > 0 && (
        <>
          <p className="text-caption text-text-muted">
            {meetings.length} proposal{meetings.length !== 1 ? 's' : ''}
          </p>

          {meetings.length === 0 ? (
            <div className="card p-6 text-center">
              <Calendar className="mx-auto text-text-muted mb-3" size={32} />
              <p className="text-body text-text-secondary">No pending meeting proposals</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {meetings.map((meeting) => (
                <MeetingCard
                  key={meeting.id}
                  meeting={meeting}
                  onConfirm={() => handleConfirm(meeting.id)}
                  onCancel={() => handleCancel(meeting.id)}
                  onView={() => setSelectedMeeting(meeting)}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Detail modal */}
      {selectedMeeting && (
        <MeetingDetailModal
          meeting={selectedMeeting}
          onClose={() => setSelectedMeeting(null)}
          onConfirm={() => handleConfirm(selectedMeeting.id)}
          onCancel={() => handleCancel(selectedMeeting.id)}
        />
      )}
    </div>
  );
}
