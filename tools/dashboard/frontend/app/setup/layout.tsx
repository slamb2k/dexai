import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'DexAI Setup',
  description: 'Set up your DexAI personal assistant',
};

export default function SetupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Setup has its own full-screen layout without sidebar/topbar
  return <>{children}</>;
}
