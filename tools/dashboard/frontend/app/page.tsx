'use client';

import { useEffect, useState, useCallback } from 'react';
import { Activity, Zap, Cpu, Database, AlertCircle } from 'lucide-react';

// Crystal Dark components
import {
  CrystalCard,
  ExpandableMetricsRow,
  CurrentStepPanel,
  EnergyWidgetCompact,
  ServicesWidgetCompact,
  SkillsWidgetCompact,
} from '@/components/crystal';
import type { CurrentStep, MetricItem } from '@/components/crystal';

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

  // Metrics state
  const [uptime, setUptime] = useState<string>('--');
  const [avgResponse, setAvgResponse] = useState<string>('--');
  const [tasksWeek, setTasksWeek] = useState<number>(0);
  const [providersActive, setProvidersActive] = useState<string>('--');

  // Build metrics array for expandable row
  const metrics: MetricItem[] = [
    {
      icon: Activity,
      label: 'System Uptime',
      value: uptime,
      sub: 'Last 30 days',
      trend: { value: 0.1, direction: 'up' },
    },
    {
      icon: Zap,
      label: 'Avg Response',
      value: avgResponse,
      sub: 'Last hour',
      trend: { value: 12, direction: 'down' },
    },
    {
      icon: Cpu,
      label: 'Tasks Completed',
      value: tasksWeek.toLocaleString(),
      sub: 'This week',
      trend: { value: 8, direction: 'up' },
    },
    {
      icon: Database,
      label: 'Active Providers',
      value: providersActive,
      sub: 'Memory systems',
    },
  ];

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
    <div className="h-[calc(100vh-140px)] flex flex-col overflow-hidden">
      {/* Error banner */}
      {error && !isDemo && (
        <div className="flex-shrink-0 mb-3 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-2 flex items-center gap-3">
          <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {/* Expandable Metrics Row */}
      <section className="flex-shrink-0 mb-4">
        <ExpandableMetricsRow metrics={metrics} />
      </section>

      {/* Main Content - 7/5 Grid Split */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-4 min-h-0 overflow-hidden">
        {/* Left Column - Chat Panel */}
        <div className="lg:col-span-7 flex flex-col min-h-0 overflow-hidden">
          <CrystalCard padding="none" className="h-full flex flex-col overflow-hidden">
            <QuickChat
              showHistory={true}
              conversationId={conversationId}
              onConversationChange={setConversationId}
              onStateChange={handleChatStateChange}
              placeholder="Type a message..."
              isConnected={isConnected}
              className="h-full"
            />
          </CrystalCard>
        </div>

        {/* Right Column - Current Step & Compact Widgets */}
        <div className="lg:col-span-5 flex flex-col gap-3 overflow-y-auto">
          {/* Current Step Panel - ADHD Focus Feature with Flow Mode */}
          <CurrentStepPanel
            step={currentStep}
            onComplete={handleStepComplete}
            onSkip={handleStepSkip}
            onStuck={handleStepStuck}
            isLoading={isLoading}
            showFlowMode={true}
          />

          {/* Compact Sidebar Widgets */}
          <EnergyWidgetCompact />
          <ServicesWidgetCompact />
          <SkillsWidgetCompact />
        </div>
      </div>
    </div>
  );
}
