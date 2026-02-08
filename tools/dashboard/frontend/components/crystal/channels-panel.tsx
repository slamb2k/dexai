'use client';

import { useEffect, useState } from 'react';
import {
  MessageSquare,
  Send,
  Phone,
  Hash,
  MessageCircle,
  Radio,
  Clock,
} from 'lucide-react';
import { CrystalCard, CrystalCardHeader, CrystalCardContent } from './crystal-card';
import { api, ServiceStatus } from '@/lib/api';
import { cn } from '@/lib/utils';
import { LucideIcon } from 'lucide-react';

interface ChannelConfig {
  id: string;
  name: string;
  icon: LucideIcon;
  comingSoon?: boolean;
}

const CHANNELS: ChannelConfig[] = [
  { id: 'chat', name: 'Chat', icon: MessageSquare },
  { id: 'telegram', name: 'Telegram', icon: Send },
  { id: 'whatsapp', name: 'WhatsApp', icon: Phone, comingSoon: true },
  { id: 'discord', name: 'Discord', icon: Hash },
  { id: 'slack', name: 'Slack', icon: MessageCircle },
];

interface ChannelsPanelProps {
  className?: string;
}

export function ChannelsPanel({ className }: ChannelsPanelProps) {
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchServices = async () => {
      try {
        const res = await api.getServices();
        if (res.success && res.data) {
          setServices(res.data);
        }
      } catch (e) {
        console.error('Failed to fetch services:', e);
      }
      setIsLoading(false);
    };

    fetchServices();
  }, []);

  const getChannelStatus = (channelId: string): 'connected' | 'disconnected' | 'coming-soon' => {
    const channel = CHANNELS.find((c) => c.id === channelId);
    if (channel?.comingSoon) return 'coming-soon';

    // Chat is always considered connected
    if (channelId === 'chat') return 'connected';

    const service = services.find((s) => s.name === channelId);
    return service?.connected ? 'connected' : 'disconnected';
  };

  const connectedCount = CHANNELS.filter(
    (c) => !c.comingSoon && getChannelStatus(c.id) === 'connected'
  ).length;

  return (
    <CrystalCard padding="none" className={className}>
      <div className="p-6">
        <CrystalCardHeader
          icon={<Radio className="w-5 h-5" />}
          title="Communication Channels"
          subtitle={`${connectedCount} active`}
        />
      </div>

      <CrystalCardContent className="px-6 pb-6 pt-0">
        <div className="flex items-center justify-between gap-2">
          {CHANNELS.map((channel) => (
            <ChannelIcon
              key={channel.id}
              channel={channel}
              status={getChannelStatus(channel.id)}
              isLoading={isLoading && channel.id !== 'chat'}
            />
          ))}
        </div>

        {/* Legend */}
        <div className="flex items-center justify-center gap-4 mt-4 pt-4 border-t border-white/[0.04]">
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span className="text-xs text-white/40">Connected</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-white/20" />
            <span className="text-xs text-white/40">Disconnected</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Clock className="w-3 h-3 text-white/20" />
            <span className="text-xs text-white/40">Coming Soon</span>
          </div>
        </div>
      </CrystalCardContent>
    </CrystalCard>
  );
}

interface ChannelIconProps {
  channel: ChannelConfig;
  status: 'connected' | 'disconnected' | 'coming-soon';
  isLoading: boolean;
}

function ChannelIcon({ channel, status, isLoading }: ChannelIconProps) {
  const Icon = channel.icon;

  return (
    <div className="flex flex-col items-center gap-2">
      <button
        disabled={status === 'coming-soon'}
        className={cn(
          'relative p-4 rounded-xl transition-all duration-200',
          'border',
          status === 'connected' && [
            'bg-emerald-500/[0.08] border-emerald-500/20',
            'hover:bg-emerald-500/[0.12] hover:border-emerald-500/30',
          ],
          status === 'disconnected' && [
            'bg-white/[0.02] border-white/[0.06]',
            'hover:bg-white/[0.04] hover:border-white/[0.08]',
          ],
          status === 'coming-soon' && [
            'bg-white/[0.01] border-white/[0.03] cursor-not-allowed opacity-50',
          ]
        )}
      >
        <Icon
          className={cn(
            'w-5 h-5',
            status === 'connected' && 'text-emerald-400',
            status === 'disconnected' && 'text-white/40',
            status === 'coming-soon' && 'text-white/20'
          )}
        />

        {/* Status dot */}
        <div
          className={cn(
            'absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full border-2 border-black',
            status === 'connected' && 'bg-emerald-400',
            status === 'disconnected' && 'bg-white/20',
            status === 'coming-soon' && 'hidden'
          )}
        />

        {/* Loading overlay */}
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50 rounded-xl">
            <div className="w-4 h-4 border-2 border-white/20 border-t-white/60 rounded-full animate-spin" />
          </div>
        )}

        {/* Coming soon badge */}
        {status === 'coming-soon' && (
          <div className="absolute -top-1 -right-1">
            <Clock className="w-3 h-3 text-white/30" />
          </div>
        )}
      </button>

      <span
        className={cn(
          'text-xs',
          status === 'connected' && 'text-white/60',
          status === 'disconnected' && 'text-white/40',
          status === 'coming-soon' && 'text-white/20'
        )}
      >
        {channel.name}
      </span>
    </div>
  );
}
