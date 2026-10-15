import type { Metadata } from 'next';
import '../frontend/src/app/globals.css';

export const metadata: Metadata = {
  title: 'SME Finance Copilot',
  description: 'Autonomous financial participant for SME cash runway diagnostics and working capital.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
