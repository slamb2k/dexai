'use client';

import { useEffect, useState, useCallback } from 'react';
import { Activity, Zap, Cpu, Database, MessageSquare, AlertCircle } from 'lucide-react';

// Crystal Dark components
import {
  CrystalCard,
  CrystalCardHeader,
  CrystalCardContent,
  MetricsCard,
  CurrentStepPanel,
  SkillsPanel,
  MemoryProvidersPanel,
  OfficePanel,
  ChannelsPanel,
} from '@/components/crystal';
import type { CurrentStep } from '@/components/crystal';

// Energy level type for API compatibility
type EnergyLevel = 'low' | 'medium' | 'high';
import { QuickChat } from '@/components/quick-chat';

// Utilities and API
import { cn } from '@/lib/utils';
import { useDexStore, useActivityStore, useMetricsStore } from '@/lib/store';
import { api } from '@/lib/api';
import { socketClient } from '@/lib/socket';

const isDemo = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

// Demo data for development
const demoCurrentStep: CurrentStep = {
  id: '1',
  title: "Reply to Sarah's email about the Q4 report",
  description: 'She asked for the updated projections by end of day',
  energyRequired: 'low',
  estimatedTime: '5 min',
  category: 'Email',
};

export default function HomePage() {
  const { avatarState, setAvatarState, setCurrentTask } = useDexStore();
  const { isConnected, setConnected } = useActivityStore();
  const { updateMetrics } = useMetricsStore();

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState<CurrentStep | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [uptime, setUptime] = useState<string>('--');
  const [avgResponse, setAvgResponse] = useState<string>('--');
  const [tasksWeek, setTasksWeek] = useState<number>(0);
  const [providersActive, setProvidersActive] = useState<string>('--');
  const [userInitials, setUserInitials] = useState<string>('U');

  // Load initial data
  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      setError(null);

      try {
        // Fetch status
        const statusRes = await api.getStatus();
        if (statusRes.success && statusRes.data) {
          setAvatarState(statusRes.data.state as 'idle' | 'thinking' | 'working');
          setCurrentTask(statusRes.data.currentTask || null);

          // Calculate uptime percentage (mock: 99.9% if connected)
          if (statusRes.data.uptime) {
            const uptimeHours = statusRes.data.uptime / 3600;
            if (uptimeHours > 24) {
              setUptime('99.9%');
            } else {
              setUptime('99.5%');
            }
          } else {
            setUptime('99.9%');
          }
        }

        // Fetch current task
        const currentTaskRes = await api.getCurrentTask();
        if (currentTaskRes.success && currentTaskRes.data?.current_task) {
          const task = currentTaskRes.data.current_task;
          setCurrentStep({
            id: task.id,
            title: task.title,
            description: task.description,
            energyRequired: (task.energy_required as EnergyLevel) || 'medium',
            estimatedTime: task.estimated_time,
            category: task.category,
          });
        }

        // Fetch metrics for response time and task count
        const metricsRes = await api.getMetricsSummary();
        if (metricsRes.success && metricsRes.data) {
          const data = metricsRes.data;
          setAvgResponse(`${data.avgResponseTime || 45}ms`);
          setTasksWeek(data.tasksWeek || 0);

          const apiMetrics = data as unknown as {
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

        // Fetch memory providers count
        const providersRes = await api.getMemoryProviders();
        if (providersRes.success && providersRes.data) {
          const active = providersRes.data.active_count || 0;
          const total = providersRes.data.providers?.length || 0;
          setProvidersActive(`${active}/${total}`);
        }

        // Fetch user settings for initials
        const setupRes = await api.getSetupState();
        if (setupRes.success && setupRes.data?.user_name) {
          const name = setupRes.data.user_name;
          const parts = name.trim().split(/\s+/);
          if (parts.length === 1) {
            setUserInitials(parts[0].charAt(0).toUpperCase());
          } else {
            setUserInitials(
              (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase()
            );
          }
        }

        // Use demo data in demo mode if no real data
        if (isDemo && !currentStep) {
          setCurrentStep(demoCurrentStep);
        }
      } catch (e) {
        const errorMsg = e instanceof Error ? e.message : 'Failed to load data';
        setError(errorMsg);

        if (isDemo) {
          setCurrentStep(demoCurrentStep);
          setUptime('99.9%');
          setAvgResponse('45ms');
          setTasksWeek(2847);
          setProvidersActive('3/5');
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
      setAvatarState(event.state as 'idle' | 'thinking' | 'working');
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
  const handleStepComplete = useCallback(async () => {
    if (currentStep?.id) {
      try {
        await api.completeTask(currentStep.id);
        setCurrentStep(null);
        setAvatarState('idle');

        const res = await api.getCurrentTask();
        if (res.success && res.data?.current_task) {
          const task = res.data.current_task;
          setCurrentStep({
            id: task.id,
            title: task.title,
            description: task.description,
            energyRequired: (task.energy_required as EnergyLevel) || 'medium',
            estimatedTime: task.estimated_time,
            category: task.category,
          });
        }
      } catch (e) {
        console.error('Failed to complete task:', e);
      }
    } else {
      setCurrentStep(null);
    }
  }, [currentStep, setAvatarState]);

  const handleStepSkip = useCallback(async () => {
    if (currentStep?.id) {
      try {
        await api.skipTask(currentStep.id);

        const res = await api.getCurrentTask();
        if (res.success && res.data?.current_task) {
          const task = res.data.current_task;
          setCurrentStep({
            id: task.id,
            title: task.title,
            description: task.description,
            energyRequired: (task.energy_required as EnergyLevel) || 'medium',
            estimatedTime: task.estimated_time,
            category: task.category,
          });
        } else {
          setCurrentStep(null);
        }
      } catch (e) {
        console.error('Failed to skip task:', e);
        setCurrentStep(null);
      }
    } else {
      setCurrentStep(null);
    }
  }, [currentStep]);

  const handleStepStuck = useCallback(async () => {
    if (currentStep?.id) {
      setAvatarState('thinking');
      try {
        await api.markTaskStuck(currentStep.id);
      } catch (e) {
        console.error('Failed to mark stuck:', e);
      }
      setTimeout(() => setAvatarState('idle'), 2000);
    }
  }, [currentStep, setAvatarState]);

  const handleChatStateChange = useCallback(
    (state: 'idle' | 'thinking' | 'working') => {
      setAvatarState(state);
    },
    [setAvatarState]
  );

  return (
    <div className="space-y-8">
      {/* Error banner */}
      {error && !isDemo && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-2xl px-4 py-3 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {/* Metrics Row */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricsCard
          icon={Activity}
          label="System Uptime"
          value={uptime}
          sub="Last 30 days"
          trend={{ value: 0.1, direction: 'up' }}
        />
        <MetricsCard
          icon={Zap}
          label="Avg Response"
          value={avgResponse}
          sub="Last hour"
          trend={{ value: 12, direction: 'down' }}
        />
        <MetricsCard
          icon={Cpu}
          label="Tasks Completed"
          value={tasksWeek.toLocaleString()}
          sub="This week"
          trend={{ value: 8, direction: 'up' }}
        />
        <MetricsCard
          icon={Database}
          label="Active Providers"
          value={providersActive}
          sub="Memory systems"
        />
      </section>

      {/* Main Content - 7/5 Grid Split */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Column - Chat Panel */}
        <div className="lg:col-span-7">
          <CrystalCard padding="none" className="h-full flex flex-col min-h-[600px]">
            {/* Chat Header */}
            <div className="p-6 border-b border-white/[0.04]">
              <CrystalCardHeader
                icon={<MessageSquare className="w-5 h-5" />}
                title="Direct Chat"
                border={false}
                action={
                  <div className="flex items-center gap-2 text-sm text-white/40">
                    <div
                      className={cn(
                        'w-1.5 h-1.5 rounded-full',
                        isConnected ? 'bg-emerald-400' : 'bg-red-400'
                      )}
                    />
                    {isConnected ? 'Active' : 'Offline'}
                  </div>
                }
              />
            </div>

            {/* Chat Area */}
            <CrystalCardContent className="flex-1 p-6 flex flex-col">
              <QuickChat
                showHistory={true}
                conversationId={conversationId}
                onConversationChange={setConversationId}
                onStateChange={handleChatStateChange}
                isProcessing={avatarState === 'thinking' || avatarState === 'working'}
                placeholder="Type a message..."
                userInitials={userInitials}
              />
            </CrystalCardContent>
          </CrystalCard>
        </div>

        {/* Right Column - Current Step, Skills & Memory Providers */}
        <div className="lg:col-span-5 space-y-6">
          {/* Current Step Panel - ADHD Focus Feature */}
          <CurrentStepPanel
            step={currentStep}
            onComplete={handleStepComplete}
            onSkip={handleStepSkip}
            onStuck={handleStepStuck}
            isLoading={isLoading}
          />
          <SkillsPanel maxDisplay={4} />
          <MemoryProvidersPanel />
        </div>
      </div>

      {/* Bottom Row - Office & Channels */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <OfficePanel />
        <ChannelsPanel />
      </section>
    </div>
  );
}
