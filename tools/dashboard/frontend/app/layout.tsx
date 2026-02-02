import type { Metadata } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import { Sidebar } from '@/components/sidebar';
import { TopBar } from '@/components/top-bar';
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
        <div className="flex h-screen overflow-hidden">
          {/* Sidebar navigation */}
          <Sidebar />

          {/* Main content area */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Top bar */}
            <TopBar />

            {/* Page content */}
            <main className="flex-1 overflow-y-auto p-6">
              {children}
            </main>
          </div>
        </div>
        {/* Toast notifications */}
        <ToastContainer />
      </body>
    </html>
  );
}
