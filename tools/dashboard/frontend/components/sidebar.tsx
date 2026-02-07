'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Home,
  CheckSquare,
  Brain,
  MessageSquare,
  Mail,
  Activity,
  Settings,
  Bug,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  LucideIcon,
} from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/lib/utils';

interface NavItem {
  href: string;
  icon: LucideIcon;
  label: string;
  badge?: number;
  admin?: boolean;
}

const navItems: NavItem[] = [
  { href: '/', icon: Home, label: 'Home' },
  { href: '/tasks', icon: CheckSquare, label: 'Tasks' },
  { href: '/memory', icon: Brain, label: 'Memory' },
  { href: '/channels', icon: MessageSquare, label: 'Channels' },
  { href: '/office', icon: Mail, label: 'Office' },
  { href: '/activity', icon: Activity, label: 'Activity' },
];

const bottomNavItems: NavItem[] = [
  { href: '/settings', icon: Settings, label: 'Settings' },
  { href: '/debug', icon: Bug, label: 'Debug', admin: true },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        'flex flex-col transition-all duration-300 ease-in-out',
        'bg-bg-surface/50 backdrop-blur-crystal',
        'border-r border-border-default',
        collapsed ? 'w-16' : 'w-56'
      )}
    >
      {/* Logo */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-border-default">
        {!collapsed && (
          <Link href="/" className="flex items-center gap-2 group">
            <div className="w-8 h-8 rounded-lg bg-accent-primary/20 flex items-center justify-center group-hover:bg-accent-primary/30 transition-colors">
              <Sparkles className="w-4 h-4 text-accent-primary" />
            </div>
            <span className="text-section-header font-semibold text-text-primary">
              DexAI
            </span>
          </Link>
        )}
        {collapsed && (
          <Link href="/" className="mx-auto">
            <div className="w-8 h-8 rounded-lg bg-accent-primary/20 flex items-center justify-center hover:bg-accent-primary/30 transition-colors">
              <Sparkles className="w-4 h-4 text-accent-primary" />
            </div>
          </Link>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className={cn(
            'p-1.5 rounded-lg transition-colors',
            'text-text-muted hover:text-text-primary hover:bg-bg-hover',
            collapsed && 'hidden'
          )}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <ChevronLeft size={18} />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 overflow-y-auto">
        <ul className="space-y-1 px-2">
          {navItems.map((item) => (
            <NavLink
              key={item.href}
              item={item}
              pathname={pathname}
              collapsed={collapsed}
            />
          ))}
        </ul>
      </nav>

      {/* Bottom section */}
      <div className="border-t border-border-default py-4">
        <ul className="space-y-1 px-2">
          {bottomNavItems.map((item) => (
            <NavLink
              key={item.href}
              item={item}
              pathname={pathname}
              collapsed={collapsed}
            />
          ))}
        </ul>

        {/* Version info */}
        {!collapsed && (
          <div className="px-4 mt-4">
            <p className="text-caption text-text-disabled">
              DexAI v0.1.0
            </p>
          </div>
        )}
      </div>

      {/* Expand button when collapsed */}
      {collapsed && (
        <button
          onClick={() => setCollapsed(false)}
          className="p-4 text-text-muted hover:text-text-primary transition-colors"
          aria-label="Expand sidebar"
        >
          <ChevronRight size={18} className="mx-auto" />
        </button>
      )}
    </aside>
  );
}

function NavLink({
  item,
  pathname,
  collapsed,
}: {
  item: NavItem;
  pathname: string;
  collapsed: boolean;
}) {
  const isActive = pathname === item.href;
  const Icon = item.icon;

  return (
    <li>
      <Link
        href={item.href}
        className={cn(
          'flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200',
          isActive
            ? 'bg-accent-muted text-accent-primary'
            : 'text-text-secondary hover:text-text-primary hover:bg-bg-hover',
          collapsed && 'justify-center px-2'
        )}
        title={collapsed ? item.label : undefined}
      >
        <Icon
          size={20}
          className={cn(
            'flex-shrink-0 transition-colors',
            isActive && 'text-accent-primary'
          )}
        />
        {!collapsed && (
          <>
            <span className="text-body flex-1">{item.label}</span>
            {item.badge !== undefined && item.badge > 0 && (
              <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-accent-primary text-white">
                {item.badge}
              </span>
            )}
            {isActive && (
              <span className="w-1.5 h-1.5 rounded-full bg-accent-primary" />
            )}
          </>
        )}
      </Link>
    </li>
  );
}
