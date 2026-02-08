'use client';

import { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface CrystalCardProps {
  children: ReactNode;
  className?: string;
  variant?: 'default' | 'elevated' | 'subtle';
  padding?: 'none' | 'sm' | 'md' | 'lg';
  hover?: boolean;
}

const variantStyles = {
  default: 'bg-white/[0.02] border-white/[0.06]',
  elevated: 'bg-white/[0.04] border-white/[0.08]',
  subtle: 'bg-white/[0.01] border-white/[0.04]',
};

const paddingStyles = {
  none: '',
  sm: 'p-4',
  md: 'p-6',
  lg: 'p-8',
};

export function CrystalCard({
  children,
  className,
  variant = 'default',
  padding = 'md',
  hover = false,
}: CrystalCardProps) {
  return (
    <div
      className={cn(
        'backdrop-blur-xl border rounded-2xl',
        variantStyles[variant],
        paddingStyles[padding],
        hover && 'transition-all duration-300 hover:bg-white/[0.04] hover:border-white/[0.08]',
        className
      )}
    >
      {children}
    </div>
  );
}

// Header variant for cards with title sections
interface CrystalCardHeaderProps {
  icon?: ReactNode;
  title: string;
  subtitle?: string;
  action?: ReactNode;
  border?: boolean;
}

export function CrystalCardHeader({ icon, title, subtitle, action, border = true }: CrystalCardHeaderProps) {
  return (
    <div className={cn('flex items-center justify-between', border && 'pb-4 border-b border-white/[0.04]')}>
      <div className="flex items-center gap-3">
        {icon && <div className="text-white/40">{icon}</div>}
        <div>
          <h3 className="font-medium text-white/90">{title}</h3>
          {subtitle && <p className="text-xs text-white/40 mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {action && <div>{action}</div>}
    </div>
  );
}

// Content wrapper for consistent spacing after header
export function CrystalCardContent({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn('pt-4', className)}>{children}</div>;
}
