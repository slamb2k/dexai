'use client';

import { cn } from '@/lib/utils';

export type AvatarState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'working'
  | 'success'
  | 'error'
  | 'sleeping'
  | 'hyperfocus'
  | 'waiting';

interface DexAvatarProps {
  state: AvatarState;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  showLabel?: boolean;
  currentTask?: string;
}

const sizeConfig = {
  sm: { container: 48, avatar: 40, eye: 4, particle: 3 },
  md: { container: 80, avatar: 64, eye: 6, particle: 4 },
  lg: { container: 120, avatar: 96, eye: 8, particle: 5 },
  xl: { container: 200, avatar: 160, eye: 12, particle: 6 },
};

// Using CSS variables for theme-aware colors
const stateConfig: Record<
  AvatarState,
  {
    color: string;
    glowColor: string;
    label: string;
    eyeState: 'open' | 'half' | 'closed';
    expression: 'neutral' | 'happy' | 'concerned' | 'determined' | 'alert' | 'patient';
    cssColor: string;
  }
> = {
  idle: {
    color: '#10b981', // Emerald - accent-primary
    glowColor: 'rgba(16, 185, 129, 0.3)',
    label: 'Ready to help',
    eyeState: 'open',
    expression: 'neutral',
    cssColor: 'var(--accent-primary)',
  },
  listening: {
    color: '#34d399', // Lighter emerald
    glowColor: 'rgba(52, 211, 153, 0.4)',
    label: 'Listening',
    eyeState: 'open',
    expression: 'alert',
    cssColor: 'var(--accent-glow)',
  },
  thinking: {
    color: '#06b6d4', // Cyan
    glowColor: 'rgba(6, 182, 212, 0.4)',
    label: 'Thinking',
    eyeState: 'half',
    expression: 'determined',
    cssColor: 'var(--accent-secondary)',
  },
  working: {
    color: '#10b981',
    glowColor: 'rgba(16, 185, 129, 0.5)',
    label: 'Working',
    eyeState: 'open',
    expression: 'determined',
    cssColor: 'var(--accent-primary)',
  },
  success: {
    color: '#10b981',
    glowColor: 'rgba(16, 185, 129, 0.5)',
    label: 'Done!',
    eyeState: 'open',
    expression: 'happy',
    cssColor: 'var(--status-success)',
  },
  error: {
    color: '#ef4444',
    glowColor: 'rgba(239, 68, 68, 0.4)',
    label: 'Something went wrong',
    eyeState: 'open',
    expression: 'concerned',
    cssColor: 'var(--status-error)',
  },
  sleeping: {
    color: '#10b981',
    glowColor: 'rgba(16, 185, 129, 0.1)',
    label: 'Sleeping',
    eyeState: 'closed',
    expression: 'neutral',
    cssColor: 'var(--accent-primary)',
  },
  hyperfocus: {
    color: '#a855f7',
    glowColor: 'rgba(168, 85, 247, 0.4)',
    label: 'In the zone',
    eyeState: 'open',
    expression: 'determined',
    cssColor: 'var(--status-hyperfocus)',
  },
  waiting: {
    color: '#f59e0b',
    glowColor: 'rgba(245, 158, 11, 0.4)',
    label: 'Waiting',
    eyeState: 'half',
    expression: 'patient',
    cssColor: 'var(--status-warning)',
  },
};

export function DexAvatar({
  state,
  size = 'md',
  showLabel = true,
  currentTask,
}: DexAvatarProps) {
  const config = stateConfig[state];
  const sizes = sizeConfig[size];

  return (
    <div className="flex flex-col items-center gap-4">
      {/* Avatar container */}
      <div
        className="relative flex items-center justify-center"
        style={{ width: sizes.container, height: sizes.container }}
      >
        {/* Outer glow ring */}
        <div
          className={cn(
            'absolute inset-0 rounded-full transition-all duration-500',
            state === 'idle' && 'animate-pulse-slow',
            state === 'thinking' && 'animate-spin-slow',
            state === 'working' && 'animate-pulse',
            state === 'success' && 'animate-scale-in',
            state === 'error' && 'animate-pulse',
            state === 'sleeping' && 'animate-pulse-slow opacity-30',
            state === 'hyperfocus' && 'animate-glow'
          )}
          style={{
            background: `radial-gradient(circle, ${config.glowColor} 0%, transparent 70%)`,
          }}
        />

        {/* Particle ring */}
        {(state === 'thinking' || state === 'working') && (
          <ParticleRing
            size={sizes.container}
            color={config.color}
            speed={state === 'thinking' ? 'slow' : 'fast'}
          />
        )}

        {/* Main avatar circle */}
        <div
          className="relative rounded-full flex items-center justify-center transition-all duration-300"
          style={{
            width: sizes.avatar,
            height: sizes.avatar,
            borderWidth: 2,
            borderStyle: 'solid',
            borderColor: config.color,
            backgroundColor: 'var(--bg-surface)',
            boxShadow: `0 0 30px ${config.glowColor}`,
          }}
        >
          {/* Face */}
          <svg
            viewBox="0 0 100 100"
            className="w-full h-full p-2"
            style={{ color: config.color }}
          >
            {/* Eyes */}
            <Eyes
              state={config.eyeState}
              color={config.color}
              expression={config.expression}
            />

            {/* Expression/mouth */}
            <Expression type={config.expression} color={config.color} />

            {/* State-specific overlays */}
            {state === 'success' && <CheckmarkOverlay color={config.color} />}
            {state === 'error' && <WarningOverlay color={config.color} />}
            {state === 'hyperfocus' && <ShieldOverlay color={config.color} />}
            {state === 'waiting' && <HourglassOverlay color={config.color} />}
            {state === 'listening' && <SoundWaveOverlay color={config.color} />}
          </svg>
        </div>
      </div>

      {/* Label */}
      {showLabel && (
        <div className="text-center">
          <p
            className="text-card-title font-medium"
            style={{ color: config.color }}
          >
            {config.label}
          </p>
          {currentTask && (
            <p className="text-caption text-text-muted mt-1 max-w-[250px] truncate">
              {currentTask}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// Eyes component
function Eyes({
  state,
  color,
}: {
  state: 'open' | 'half' | 'closed';
  color: string;
  expression: string;
}) {
  const eyeY = 38;
  const leftEyeX = 35;
  const rightEyeX = 65;

  if (state === 'closed') {
    return (
      <g>
        <line
          x1={leftEyeX - 6}
          y1={eyeY}
          x2={leftEyeX + 6}
          y2={eyeY}
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
        />
        <line
          x1={rightEyeX - 6}
          y1={eyeY}
          x2={rightEyeX + 6}
          y2={eyeY}
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
        />
      </g>
    );
  }

  const eyeHeight = state === 'half' ? 4 : 8;

  return (
    <g>
      <ellipse cx={leftEyeX} cy={eyeY} rx={6} ry={eyeHeight} fill={color} />
      <ellipse cx={rightEyeX} cy={eyeY} rx={6} ry={eyeHeight} fill={color} />
      {/* Highlights */}
      {state === 'open' && (
        <>
          <circle cx={leftEyeX + 2} cy={eyeY - 2} r={2} fill="white" opacity={0.6} />
          <circle cx={rightEyeX + 2} cy={eyeY - 2} r={2} fill="white" opacity={0.6} />
        </>
      )}
    </g>
  );
}

// Expression/mouth component
function Expression({ type, color }: { type: string; color: string }) {
  const mouthY = 60;

  switch (type) {
    case 'happy':
      return (
        <path
          d="M 35 58 Q 50 72 65 58"
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinecap="round"
        />
      );
    case 'concerned':
      return (
        <path
          d="M 35 65 Q 50 58 65 65"
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinecap="round"
        />
      );
    case 'determined':
      return (
        <line
          x1={38}
          y1={mouthY}
          x2={62}
          y2={mouthY}
          stroke={color}
          strokeWidth="3"
          strokeLinecap="round"
        />
      );
    case 'alert':
      return (
        <ellipse cx={50} cy={mouthY} rx={4} ry={3} fill={color} />
      );
    case 'patient':
      return (
        <path
          d="M 40 60 Q 50 64 60 60"
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
        />
      );
    default:
      return (
        <path
          d="M 40 60 Q 50 65 60 60"
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
        />
      );
  }
}

// Particle ring for thinking/working states
function ParticleRing({
  size,
  color,
  speed,
}: {
  size: number;
  color: string;
  speed: 'slow' | 'fast';
}) {
  const numParticles = 8;
  const radius = size / 2 - 4;

  return (
    <div
      className={cn(
        'absolute inset-0',
        speed === 'slow' ? 'animate-spin-slow' : 'animate-spin'
      )}
      style={{ animationDuration: speed === 'slow' ? '8s' : '3s' }}
    >
      {Array.from({ length: numParticles }).map((_, i) => {
        const angle = (i / numParticles) * Math.PI * 2;
        const x = Math.cos(angle) * radius + size / 2;
        const y = Math.sin(angle) * radius + size / 2;

        return (
          <div
            key={i}
            className="absolute w-1.5 h-1.5 rounded-full"
            style={{
              left: x - 3,
              top: y - 3,
              backgroundColor: color,
              opacity: 0.6 + (i % 2) * 0.4,
            }}
          />
        );
      })}
    </div>
  );
}

// Overlay components for special states
function CheckmarkOverlay({ color }: { color: string }) {
  return (
    <g className="animate-scale-in">
      <circle cx={75} cy={25} r={12} fill="var(--bg-primary)" stroke={color} strokeWidth="2" />
      <path
        d="M 69 25 L 73 29 L 81 21"
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </g>
  );
}

function WarningOverlay({ color }: { color: string }) {
  return (
    <g className="animate-pulse">
      <circle cx={75} cy={25} r={12} fill="var(--bg-primary)" stroke={color} strokeWidth="2" />
      <text x={75} y={30} textAnchor="middle" fill={color} fontSize="14" fontWeight="bold">
        !
      </text>
    </g>
  );
}

function ShieldOverlay({ color }: { color: string }) {
  return (
    <g opacity={0.3}>
      <path
        d="M 50 15 L 25 25 L 25 50 Q 25 75 50 85 Q 75 75 75 50 L 75 25 Z"
        fill="none"
        stroke={color}
        strokeWidth="2"
      />
    </g>
  );
}

function HourglassOverlay({ color }: { color: string }) {
  return (
    <g className="animate-pulse" opacity={0.5}>
      <path
        d="M 80 15 L 80 20 L 75 25 L 80 30 L 80 35 M 70 15 L 70 20 L 75 25 L 70 30 L 70 35"
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </g>
  );
}

function SoundWaveOverlay({ color }: { color: string }) {
  return (
    <g className="animate-pulse" opacity={0.5}>
      <path
        d="M 82 35 Q 88 50 82 65"
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M 88 30 Q 96 50 88 70"
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        opacity={0.6}
      />
    </g>
  );
}
