'use client';

import { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { CrystalHeader } from './crystal-header';
import { cn } from '@/lib/utils';

interface CrystalLayoutProps {
  children: ReactNode;
  className?: string;
}

export function CrystalLayout({ children, className }: CrystalLayoutProps) {
  const pathname = usePathname();

  // Don't apply crystal layout to setup pages
  const isSetupPage = pathname?.startsWith('/setup');
  if (isSetupPage) {
    return <>{children}</>;
  }

  return (
    <div className={cn('h-screen bg-black text-white overflow-hidden', className)}>
      {/* Crystal refraction background effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        {/* Primary gradient orb - top left */}
        <div
          className={cn(
            'absolute -top-32 left-1/4',
            'w-[600px] h-[600px]',
            'rounded-full blur-3xl opacity-30',
            'bg-gradient-conic from-white/5 via-transparent to-white/5'
          )}
          style={{
            background:
              'conic-gradient(from 0deg, rgba(255,255,255,0.05), transparent 60%, rgba(255,255,255,0.03), transparent)',
          }}
        />

        {/* Secondary gradient orb - bottom right */}
        <div
          className={cn(
            'absolute -bottom-32 right-1/4',
            'w-[500px] h-[500px]',
            'rounded-full blur-3xl opacity-25'
          )}
          style={{
            background:
              'conic-gradient(from 180deg, rgba(148,163,184,0.05), transparent 60%, rgba(148,163,184,0.03), transparent)',
          }}
        />

        {/* Tertiary accent orb - center */}
        <div
          className={cn(
            'absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2',
            'w-[800px] h-[800px]',
            'rounded-full blur-[100px] opacity-10'
          )}
          style={{
            background:
              'radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 70%)',
          }}
        />
      </div>

      {/* Crystal grid pattern overlay */}
      <div
        className="fixed inset-0 opacity-[0.015] pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)
          `,
          backgroundSize: '60px 60px',
        }}
      />

      {/* Noise texture overlay for depth */}
      <div
        className="fixed inset-0 opacity-[0.02] pointer-events-none"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
        }}
      />

      {/* Header */}
      <CrystalHeader />

      {/* Main Content - scrollable container for all pages except home */}
      <main className="relative z-10 h-[calc(100vh-80px)] overflow-y-auto">
        <div className="max-w-7xl mx-auto px-8 pt-4 pb-6">
          <div className="animate-fade-in">{children}</div>
        </div>
      </main>

      {/* Bottom edge gradient */}
      <div
        className="fixed bottom-0 left-0 right-0 h-32 pointer-events-none"
        style={{
          background:
            'linear-gradient(to top, rgba(0,0,0,0.5), transparent)',
        }}
      />
    </div>
  );
}

// Animation styles that should be added to globals.css
// @keyframes fade-in {
//   from { opacity: 0; transform: translateY(10px); }
//   to { opacity: 1; transform: translateY(0); }
// }
// .animate-fade-in {
//   animation: fade-in 0.5s ease-out;
// }
