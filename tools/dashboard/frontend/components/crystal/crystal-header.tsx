'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Brain,
  Settings,
  User,
  Menu,
  X,
  Home,
  Database,
  Sparkles,
  Radio,
  Building2,
} from 'lucide-react';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

interface CrystalHeaderProps {
  className?: string;
}

const NAV_ITEMS = [
  { label: 'Overview', href: '/', icon: Home },
  { label: 'Memory', href: '/memory', icon: Database },
  { label: 'Skills', href: '/skills', icon: Sparkles },
  { label: 'Services', href: '/office', icon: Building2 },
  { label: 'Channels', href: '/channels', icon: Radio },
];

export function CrystalHeader({ className }: CrystalHeaderProps) {
  const pathname = usePathname();
  const [userName, setUserName] = useState<string>('');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    // Fetch user settings
    const fetchSettings = async () => {
      try {
        const setupRes = await api.getSetupState();
        if (setupRes.success && setupRes.data?.user_name) {
          setUserName(setupRes.data.user_name);
        }
      } catch (e) {
        console.error('Failed to fetch settings:', e);
      }
    };

    fetchSettings();
  }, []);

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
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-5">
        <div className="flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-3 sm:gap-5">
            <div
              className={cn(
                'w-10 h-10 sm:w-12 sm:h-12 rounded-xl sm:rounded-2xl',
                'bg-gradient-to-br from-white/10 to-white/5',
                'backdrop-blur-xl border border-white/10',
                'flex items-center justify-center',
                'shadow-lg shadow-white/[0.02]'
              )}
            >
              <Brain className="w-5 h-5 sm:w-6 sm:h-6 text-white/80" />
            </div>
            {/* Hide text on very small screens */}
            <div className="hidden xs:block">
              <h1 className="text-xl sm:text-2xl font-light tracking-wide text-white/90">
                DexAI
              </h1>
              <p className="text-[10px] sm:text-xs text-white/30 tracking-widest uppercase">
                Control Center
              </p>
            </div>
          </div>

          {/* Desktop Navigation Tabs - Hidden on mobile */}
          <nav className="hidden md:flex items-center gap-1">
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
                    'px-5 py-2.5 min-h-[44px] rounded-xl text-sm font-medium transition-all duration-200',
                    'flex items-center justify-center',
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
          <div className="flex items-center gap-2 sm:gap-3">
            {/* Online Status - Hide text on small screens */}
            <div
              className={cn(
                'flex items-center gap-2 sm:gap-3 px-2 sm:px-4 py-2 rounded-xl',
                'bg-emerald-500/[0.05] border border-emerald-500/20'
              )}
            >
              <div className="relative">
                <div className="w-2 h-2 rounded-full bg-emerald-400" />
                <div className="absolute inset-0 w-2 h-2 rounded-full bg-emerald-400 animate-ping opacity-75" />
              </div>
              <span className="hidden sm:inline text-sm text-emerald-300/80">Online</span>
            </div>

            {/* Settings Icon */}
            <Link href="/settings">
              <button
                className={cn(
                  'w-10 h-10 min-h-[44px] rounded-xl transition-all duration-200',
                  'bg-white/[0.04] border border-white/[0.06]',
                  'hover:bg-white/[0.08] hover:border-white/[0.10]',
                  'flex items-center justify-center'
                )}
              >
                <Settings className="w-5 h-5 text-white/40" />
              </button>
            </Link>

            {/* User Avatar - Hidden on mobile, shown in menu */}
            <button
              className={cn(
                'hidden md:flex w-10 h-10 rounded-xl items-center justify-center',
                'bg-gradient-to-br from-white/10 to-white/5',
                'border border-white/10',
                'text-sm font-medium text-white/80',
                'hover:from-white/15 hover:to-white/10 transition-all duration-200'
              )}
            >
              {userName ? getInitials(userName) : <User className="w-5 h-5" />}
            </button>

            {/* Hamburger Menu Button - Mobile Only */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className={cn(
                'md:hidden w-10 h-10 min-h-[44px] rounded-xl',
                'bg-white/[0.04] border border-white/[0.06]',
                'hover:bg-white/[0.08]',
                'flex items-center justify-center transition-all duration-200'
              )}
              aria-label="Toggle menu"
              aria-expanded={mobileMenuOpen}
            >
              {mobileMenuOpen ? (
                <X className="w-5 h-5 text-white/60" />
              ) : (
                <Menu className="w-5 h-5 text-white/60" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Menu Overlay */}
      {mobileMenuOpen && (
        <div className="md:hidden">
          <nav className="border-t border-white/[0.06] bg-black/80 backdrop-blur-xl">
            <div className="max-w-7xl mx-auto px-4 py-4 space-y-2">
              {NAV_ITEMS.map((item) => {
                const isActive =
                  item.href === '/'
                    ? pathname === '/'
                    : pathname?.startsWith(item.href);
                const Icon = item.icon;

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      'flex items-center gap-3 px-4 py-3 rounded-xl min-h-[44px]',
                      'transition-all duration-200',
                      isActive
                        ? 'bg-white/10 text-white'
                        : 'text-white/60 hover:text-white/80 hover:bg-white/[0.04]'
                    )}
                  >
                    <Icon className="w-5 h-5" />
                    {item.label}
                  </Link>
                );
              })}

              {/* User info section in mobile menu */}
              <div className="pt-4 mt-4 border-t border-white/[0.06]">
                <div className="flex items-center gap-3 px-4 py-3">
                  <div
                    className={cn(
                      'w-10 h-10 rounded-xl flex items-center justify-center',
                      'bg-gradient-to-br from-white/10 to-white/5',
                      'border border-white/10',
                      'text-sm font-medium text-white/80'
                    )}
                  >
                    {userName ? getInitials(userName) : <User className="w-5 h-5" />}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-white/90">
                      {userName || 'User'}
                    </p>
                    <p className="text-xs text-white/40">Dashboard User</p>
                  </div>
                </div>

              </div>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
