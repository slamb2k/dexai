'use client';

import { CrystalLayout } from '@/components/crystal';

/**
 * Layout wrapper for dashboard pages.
 * Uses the Crystal Dark theme layout for all pages except setup.
 */
export function LayoutContent({ children }: { children: React.ReactNode }) {
  return <CrystalLayout>{children}</CrystalLayout>;
}
