'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { PAGE_TITLE_FZ } from '@/components/common/PageHeader';
import { Button, Center, Group, Paper, Select, Skeleton, Stack, Text, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconBooks, IconLock, IconSparkles } from '@tabler/icons-react';
import { LogoMark } from '@/components/brand/LogoMark';
import { EmptyState } from '@/components/common/EmptyState';
import { GUEST_LIMIT_MESSAGES } from '@/components/common/GuestLimitTooltip';
import { QueryError } from '@/components/common/QueryError';
import { useGuestQuota } from '@/hooks/useAuth';
import { useCreateSession } from '@/hooks/useChat';
import { useDocuments } from '@/hooks/useDocuments';
import { EXAMPLE_PROMPTS } from './prompts';

export function NewChatView() {
  const router = useRouter();
  const { data: docs, isLoading, error, refetch } = useDocuments();
  const createSession = useCreateSession();
  const { canCreateSession } = useGuestQuota();
  const readyDocs = (docs ?? []).filter((d) => d.status === 'ready');
  const [documentId, setDocumentId] = useState<string | null>(null);
  const selected = documentId ?? (readyDocs.length === 1 ? readyDocs[0].id : null);

  const start = () => {
    if (!selected) return;
    createSession.mutate(selected, {
      onSuccess: (session) => router.push(`/chat/${session.id}`),
      onError: (err) => notifications.show({ color: 'red', title: 'Gagal membuat sesi', message: err.message }),
    });
  };

  let body: React.ReactNode;
  if (isLoading) {
    body = <Skeleton h={140} radius="md" />;
  } else if (error) {
    body = <QueryError error={error} onRetry={() => refetch()} />;
  } else if (!canCreateSession) {
    body = (
      <EmptyState
        icon={<IconLock size={24} aria-hidden />}
        title="Batas mode tamu tercapai"
        description={GUEST_LIMIT_MESSAGES.session}
        action={
          <Button component={Link} href="/login">
            Masuk
          </Button>
        }
      />
    );
  } else if (!readyDocs.length) {
    body = (
      <EmptyState
        icon={<IconBooks size={24} aria-hidden />}
        title="Belum ada buku yang siap"
        description={
          docs?.length
            ? 'Buku Anda masih diproses. Tunggu sampai statusnya "Siap", lalu kembali ke sini.'
            : 'Unggah buku pelajaran terlebih dahulu sebagai sumber soal.'
        }
        action={
          <Button component={Link} href="/documents">
            Ke halaman Dokumen
          </Button>
        }
      />
    );
  } else {
    body = (
      <Paper p="lg">
        <Stack gap="md">
          <Select
            label="Sumber soal"
            description="Soal hanya akan dibuat dari isi buku yang dipilih."
            placeholder="Pilih buku"
            data={readyDocs.map((d) => ({ value: d.id, label: `${d.filename} · ${d.subject}` }))}
            value={selected}
            onChange={setDocumentId}
            searchable
            nothingFoundMessage="Buku tidak ditemukan"
            leftSection={<IconBooks size={16} aria-hidden />}
          />
          <Button
            color="accent"
            size="md"
            leftSection={<IconSparkles size={18} aria-hidden />}
            disabled={!selected}
            loading={createSession.isPending}
            onClick={start}
          >
            Mulai Chat
          </Button>
        </Stack>
      </Paper>
    );
  }

  return (
    <Center mih={{ base: 'calc(100dvh - 56px)', sm: '100dvh' }} p="md">
      <Stack w="100%" maw={560} gap="lg">
        <Stack align="center" gap="xs" ta="center">
          <LogoMark size={56} />
          <Title order={1} fz={PAGE_TITLE_FZ}>
            Buat soal dari buku
          </Title>
          <Text c="dimmed" maw={460}>
            Pilih buku, lalu minta soal dengan bahasa sehari-hari. Setiap soal divalidasi terhadap isi buku.
          </Text>
        </Stack>

        {body}

        <Stack gap={6}>
          <Text size="xs" c="dimmed" ta="center" fw={600} tt="uppercase">
            Contoh permintaan
          </Text>
          <Group justify="center" gap={6}>
            {EXAMPLE_PROMPTS.map((p) => (
              <Text key={p} size="sm" c="dimmed" px="sm" py={4} bd="1px solid var(--mantine-color-default-border)" style={{ borderRadius: 999 }}>
                “{p}”
              </Text>
            ))}
          </Group>
        </Stack>
      </Stack>
    </Center>
  );
}
