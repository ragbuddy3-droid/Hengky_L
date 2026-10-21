'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { Button, Center, Code, Group } from '@mantine/core';
import { IconBug, IconRefresh } from '@tabler/icons-react';
import { EmptyState } from '@/components/common/EmptyState';
import { FULL_HEIGHT } from '@/components/layout/AppShellLayout';

/** Fallback bila terjadi error tak terduga saat merender halaman (bukan error API biasa). */
export default function AppError({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <Center mih={FULL_HEIGHT} p="md">
      <EmptyState
        icon={<IconBug size={24} aria-hidden />}
        title="Terjadi kesalahan pada halaman ini"
        description={
          <>
            Coba muat ulang bagian ini. Jika masalah berlanjut, salin pesan berikut saat melapor:
            <Code display="block" mt="xs" fz="xs">
              {error.digest ?? error.message}
            </Code>
          </>
        }
        action={
          <Group justify="center">
            <Button variant="default" component={Link} href="/chat">
              Ke Chat
            </Button>
            <Button leftSection={<IconRefresh size={16} aria-hidden />} onClick={() => retry()}>
              Coba lagi
            </Button>
          </Group>
        }
      />
    </Center>
  );
}
