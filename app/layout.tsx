import type { Metadata } from 'next';
import '../frontend/src/app/globals.css';

export const metadata: Metadata = {
  title: 'SME Cash Review',
  description: 'A synthetic-data demo for reviewing historical cash movement.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
