import type { Metadata } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import { LayoutContent } from '@/components/layout-content';
import { ToastContainer } from '@/components/toast';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
});

export const metadata: Metadata = {
  title: 'DexAI Dashboard',
  description: 'Personal AI Assistant Management Dashboard',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-bg-primary text-text-primary min-h-screen">
        <LayoutContent>{children}</LayoutContent>
        {/* Toast notifications */}
        <ToastContainer />
      </body>
    </html>
  );
}
