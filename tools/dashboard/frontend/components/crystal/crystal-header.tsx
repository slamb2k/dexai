'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Brain, Settings, User } from 'lucide-react';
import { EnergySelector } from '@/components/energy-selector';
import { FlowIndicator } from '@/components/flow-indicator';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

interface CrystalHeaderProps {
  className?: string;
}

const NAV_ITEMS = [
  { label: 'Overview', href: '/' },
  { label: 'Memory', href: '/memory' },
  { label: 'Skills', href: '/skills' },
  { label: 'Channels', href: '/channels' },
];

export function CrystalHeader({ className }: CrystalHeaderProps) {
  const pathname = usePathname();
  const [userName, setUserName] = useState<string>('');
  const [energyLevel, setEnergyLevel] = useState<'low' | 'medium' | 'high'>('medium');
  const [isInFlow, setIsInFlow] = useState(false);
  const [flowStartTime, setFlowStartTime] = useState<Date | undefined>();

  useEffect(() => {
    // Fetch user settings
    const fetchSettings = async () => {
      try {
        const setupRes = await api.getSetupState();
        if (setupRes.success && setupRes.data?.user_name) {
          setUserName(setupRes.data.user_name);
        }

        const energyRes = await api.getEnergyLevel();
        if (energyRes.success && energyRes.data) {
          setEnergyLevel(energyRes.data.level as 'low' | 'medium' | 'high');
        }

        const flowRes = await api.getFlowState();
        if (flowRes.success && flowRes.data) {
          setIsInFlow(flowRes.data.is_in_flow);
          if (flowRes.data.flow_start_time) {
            setFlowStartTime(new Date(flowRes.data.flow_start_time));
          }
        }
      } catch (e) {
        console.error('Failed to fetch settings:', e);
      }
    };

    fetchSettings();
  }, []);

  const handleEnergyChange = async (level: 'low' | 'medium' | 'high') => {
    setEnergyLevel(level);
    try {
      await api.setEnergyLevel(level);
    } catch (e) {
      console.error('Failed to save energy level:', e);
    }
  };

  const getInitials = (name: string): string => {
    if (!name) return 'U';
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) {
      return parts[0].charAt(0).toUpperCase();
    }
    return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
  };

  return (
    <header
      className={cn(
        'relative z-10 border-b border-white/[0.06]',
        'bg-black/50 backdrop-blur-xl',
        className
      )}
    >
      <div className="max-w-7xl mx-auto px-8 py-5">
        <div className="flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-5">
            <div
              className={cn(
                'w-12 h-12 rounded-2xl',
                'bg-gradient-to-br from-white/10 to-white/5',
                'backdrop-blur-xl border border-white/10',
                'flex items-center justify-center',
                'shadow-lg shadow-white/[0.02]'
              )}
            >
              <Brain className="w-6 h-6 text-white/80" />
            </div>
            <div>
              <h1 className="text-2xl font-light tracking-wide text-white/90">
                DexAI
              </h1>
              <p className="text-xs text-white/30 tracking-widest uppercase">
                Control Center
              </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => {
              const isActive =
                item.href === '/'
                  ? pathname === '/'
                  : pathname?.startsWith(item.href);

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200',
                    isActive
                      ? 'bg-white/10 text-white shadow-sm'
                      : 'text-white/40 hover:text-white/70 hover:bg-white/[0.04]'
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          {/* Right Section */}
          <div className="flex items-center gap-3">
            {/* ADHD Features - subtle integration */}
            <div className="flex items-center gap-2 pr-3 border-r border-white/[0.06]">
              <EnergySelector
                value={energyLevel}
                onChange={handleEnergyChange}
                compact
              />
              <FlowIndicator
                isInFlow={isInFlow}
                flowStartTime={flowStartTime}
                onPauseFlow={() => setIsInFlow(false)}
                compact
              />
            </div>

            {/* Online Status */}
            <div
              className={cn(
                'flex items-center gap-3 px-4 py-2 rounded-xl',
                'bg-emerald-500/[0.05] border border-emerald-500/20'
              )}
            >
              <div className="relative">
                <div className="w-2 h-2 rounded-full bg-emerald-400" />
                <div className="absolute inset-0 w-2 h-2 rounded-full bg-emerald-400 animate-ping opacity-75" />
              </div>
              <span className="text-sm text-emerald-300/80">Online</span>
            </div>

            {/* Settings Icon */}
            <Link href="/settings">
              <button
                className={cn(
                  'p-2.5 rounded-xl transition-all duration-200',
                  'bg-white/[0.04] border border-white/[0.06]',
                  'hover:bg-white/[0.08] hover:border-white/[0.10]'
                )}
              >
                <Settings className="w-5 h-5 text-white/40" />
              </button>
            </Link>

            {/* User Avatar */}
            <button
              className={cn(
                'w-10 h-10 rounded-xl flex items-center justify-center',
                'bg-gradient-to-br from-white/10 to-white/5',
                'border border-white/10',
                'text-sm font-medium text-white/80',
                'hover:from-white/15 hover:to-white/10 transition-all duration-200'
              )}
            >
              {userName ? getInitials(userName) : <User className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
