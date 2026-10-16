'use client';

import Link from 'next/link';
import { Button, Center } from '@mantine/core';
import { IconError404 } from '@tabler/icons-react';
import { EmptyState } from '@/components/common/EmptyState';

export default function NotFound() {
  return (
    <Center mih="100dvh" p="md">
      <EmptyState
        icon={<IconError404 size={24} aria-hidden />}
        title="Halaman tidak ditemukan"
        description="Alamat yang Anda buka tidak tersedia."
        action={
          <Button component={Link} href="/chat">
            Kembali ke Chat
          </Button>
        }
      />
    </Center>
  );
}
