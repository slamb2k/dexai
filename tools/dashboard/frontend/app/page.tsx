'use client';

import { useEffect, useState } from 'react';
import { DexAvatar, AvatarState } from '@/components/dex-avatar';
import { CurrentStepCard, CurrentStep, EnergyLevel } from '@/components/current-step-card';
import { EnergySelector, EnergyIndicator } from '@/components/energy-selector';
import { FlowIndicator, FlowBadge } from '@/components/flow-indicator';
import { CommitmentBadge, Commitment } from '@/components/commitment-badge';
import { QuickChat } from '@/components/quick-chat';
import { AlertCircle, History } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useDexStore, useActivityStore, useMetricsStore } from '@/lib/store';
import { api } from '@/lib/api';
import { socketClient } from '@/lib/socket';

const isDemo = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

// Demo data for development
const demoCurrentStep: CurrentStep = {
  id: '1',
  title: 'Reply to Sarah\'s email about the Q4 report',
  description: 'She asked for the updated projections by end of day',
  energyRequired: 'low',
  estimatedTime: '5 min',
  category: 'Email',
};

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
    description: 'callback',
    createdAt: new Date(),
  },
];

export default function HomePage() {
  const { avatarState, currentTask, setAvatarState, setCurrentTask } = useDexStore();
  const { isConnected, setConnected } = useActivityStore();
  const { updateMetrics } = useMetricsStore();

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [energyLevel, setEnergyLevel] = useState<EnergyLevel>('medium');
  const [isInFlow, setIsInFlow] = useState(false);
  const [flowStartTime, setFlowStartTime] = useState<Date | undefined>();
  const [currentStep, setCurrentStep] = useState<CurrentStep | null>(null);
  const [commitments, setCommitments] = useState<Commitment[]>([]);
  const [contextResume, setContextResume] = useState<{ task: string; time: string } | null>(null);

  // Load initial data
  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      setError(null);

      try {
        // Fetch status
        const statusRes = await api.getStatus();
        if (statusRes.success && statusRes.data) {
          setAvatarState(statusRes.data.state as AvatarState);
          setCurrentTask(statusRes.data.currentTask || null);

          // Map to CurrentStep format
          if (statusRes.data.currentTask) {
            setCurrentStep({
              id: '1',
              title: statusRes.data.currentTask,
              energyRequired: 'medium',
            });
          }
        }

        // Fetch metrics
        const metricsRes = await api.getMetricsSummary();
        if (metricsRes.success && metricsRes.data) {
          const apiMetrics = metricsRes.data as unknown as {
            quick_stats?: {
              tasks_today?: number;
              messages_today?: number;
              cost_today_usd?: number;
            };
          };
          const quickStats = apiMetrics.quick_stats;
          if (quickStats) {
            updateMetrics({
              tasksToday: quickStats.tasks_today ?? 0,
              messagesToday: quickStats.messages_today ?? 0,
              costToday: quickStats.cost_today_usd ?? 0,
            });
          }
        }

        // If no real data, use demo data in demo mode
        if (isDemo && !currentStep) {
          setCurrentStep(demoCurrentStep);
          setCommitments(demoCommitments);
        }
      } catch (e) {
        const errorMsg = e instanceof Error ? e.message : 'Failed to load data';
        setError(errorMsg);

        // Use demo data on error if in demo mode
        if (isDemo) {
          setCurrentStep(demoCurrentStep);
          setCommitments(demoCommitments);
        }
      }

      setIsLoading(false);
    };

    loadData();
  }, [setAvatarState, setCurrentTask, updateMetrics]);

  // WebSocket connection
  useEffect(() => {
    socketClient.connect();

    const unsubConnect = socketClient.onConnect(() => {
      setConnected(true);
    });

    const unsubDisconnect = socketClient.onDisconnect(() => {
      setConnected(false);
    });

    const unsubState = socketClient.onDexState((event) => {
      setAvatarState(event.state as AvatarState);
      setCurrentTask(event.task || null);

      if (event.task) {
        setCurrentStep({
          id: Date.now().toString(),
          title: event.task,
          energyRequired: 'medium',
        });
      }
    });

    return () => {
      unsubConnect();
      unsubDisconnect();
      unsubState();
      socketClient.disconnect();
    };
  }, [setAvatarState, setCurrentTask, setConnected]);

  // Handle step completion
  const handleStepComplete = () => {
    setCurrentStep(null);
    setAvatarState('success');
    setTimeout(() => setAvatarState('idle'), 2000);
  };

  const handleStepSkip = () => {
    setCurrentStep(null);
  };

  const handleStepStuck = () => {
    setAvatarState('thinking');
    // Trigger friction-solving in the future
  };

  const handleSendMessage = (message: string) => {
    setAvatarState('thinking');
    // Process message - for now just simulate
    setTimeout(() => {
      setAvatarState('idle');
    }, 2000);
  };

  const handleResumeContext = () => {
    // Resume from saved context
    setContextResume(null);
  };

  return (
    <div className="space-y-6 animate-fade-in max-w-4xl mx-auto">
      {/* Error banner */}
      {error && !isDemo && (
        <div className="bg-status-error/10 border border-status-error/30 rounded-2xl px-4 py-3 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-status-error flex-shrink-0" />
          <p className="text-body text-status-error">{error}</p>
        </div>
      )}

      {/* Context Resume Prompt (if returning from break) */}
      {contextResume && (
        <button
          onClick={handleResumeContext}
          className="w-full crystal-card p-4 flex items-center gap-4 hover:border-accent-primary/30 transition-colors"
        >
          <div className="w-10 h-10 rounded-xl bg-accent-muted flex items-center justify-center">
            <History className="w-5 h-5 text-accent-primary" />
          </div>
          <div className="flex-1 text-left">
            <p className="text-body text-text-primary">
              You were working on: <span className="font-medium">{contextResume.task}</span>
            </p>
            <p className="text-caption text-text-muted">
              {contextResume.time} ago • Click to resume
            </p>
          </div>
        </button>
      )}

      {/* Main Avatar Section - Large and Centered */}
      <section className="flex flex-col items-center py-8">
        <DexAvatar
          state={avatarState}
          size="xl"
          showLabel
          currentTask={currentTask || undefined}
        />
      </section>

      {/* Current Step Card - THE ONE THING */}
      <CurrentStepCard
        step={currentStep}
        onComplete={handleStepComplete}
        onSkip={handleStepSkip}
        onStuck={handleStepStuck}
        isLoading={isLoading}
      />

      {/* Status Row - Energy, Flow, Commitments */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Energy Selector */}
        <EnergySelector
          value={energyLevel}
          onChange={setEnergyLevel}
          compact
        />

        {/* Flow State Indicator */}
        <FlowIndicator
          isInFlow={isInFlow}
          flowStartTime={flowStartTime}
          onPauseFlow={() => setIsInFlow(false)}
          compact={false}
        />

        {/* Commitments - RSD-safe language */}
        <CommitmentBadge
          count={commitments.length}
          onClick={() => {
            // Navigate to memory page or show modal
          }}
        />
      </section>

      {/* Quick Chat */}
      <section>
        <QuickChat
          onSendMessage={handleSendMessage}
          isProcessing={avatarState === 'thinking' || avatarState === 'working'}
          placeholder="Ask Dex anything..."
        />
      </section>

      {/* Connection Status - Subtle */}
      <div className="flex items-center justify-center gap-2 pb-4">
        <span
          className={cn(
            'w-1.5 h-1.5 rounded-full',
            isConnected ? 'bg-status-success' : 'bg-status-error'
          )}
        />
        <span className="text-caption text-text-disabled">
          {isConnected ? 'Connected' : 'Reconnecting...'}
        </span>
      </div>
    </div>
  );
}
