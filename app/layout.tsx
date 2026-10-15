import type { Metadata } from 'next';
import '../frontend/src/app/globals.css';

export const metadata: Metadata = {
  title: 'SME Finance Copilot',
  description: 'Autonomous financial participant for SME cash runway diagnostics and working capital.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>{children}</body>
    </html>
  );
}
