import '@mantine/core/styles.css';
import '@mantine/dropzone/styles.css';
import '@mantine/notifications/styles.css';

import { ColorSchemeScript, MantineProvider, createTheme } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import AppShellLayout from '@/components/layout/AppShellLayout';

export const metadata = {
  title: 'RAG-AQG — Automatic Question Generator v3',
  description: 'Sistem pembuatan soal otomatis berbasis RAG dengan validasi 2-layer dan self-refinement.',
};

const theme = createTheme({
  primaryColor: 'blue',
  defaultRadius: 'sm',
  fontFamily: 'Inter, system-ui, sans-serif',
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="id" suppressHydrationWarning>
      <head>
        <ColorSchemeScript defaultColorScheme="auto" />
      </head>
      <body>
        <MantineProvider theme={theme} defaultColorScheme="auto">
          <Notifications position="top-right" zIndex={1000} />
          <AppShellLayout>{children}</AppShellLayout>
        </MantineProvider>
      </body>
    </html>
  );
}

