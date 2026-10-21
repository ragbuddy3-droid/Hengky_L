'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { ActionIcon, Box, Button, Group, Menu, NavLink, Paper, Skeleton, Stack, Text } from '@mantine/core';
import { IconClockHour4, IconDots, IconMessage, IconTrash } from '@tabler/icons-react';
import { useMe } from '@/hooks/useAuth';
import { useChatSessions } from '@/hooks/useChat';
import { useDeleteSessionAction } from '@/features/chat/useDeleteSessionAction';

function GuestHistoryBanner() {
  return (
    <Paper p="xs" mb="xs" radius="md" withBorder={false} bg="var(--mantine-color-accent-light)">
      <Group gap={6} align="flex-start" wrap="nowrap">
        <IconClockHour4 size={16} aria-hidden style={{ flexShrink: 0, marginTop: 2, color: 'var(--app-warning-text)' }} />
        <Text size="xs" lh={1.4}>
          Riwayat hanya tersimpan di browser ini selama 24 jam. Masuk untuk menyimpan.
        </Text>
      </Group>
      <Button component={Link} href="/login" size="compact-xs" variant="subtle" color="accent.8" mt={4} ml={16}>
        Masuk
      </Button>
    </Paper>
  );
}

export function NavbarSessions() {
  const { isGuest } = useMe();
  return (
    <>
      {isGuest && <GuestHistoryBanner />}
      <SessionList />
    </>
  );
}

function SessionList() {
  const router = useRouter();
  const params = useParams<{ sessionId?: string }>();
  const { data: sessions, isLoading, isError } = useChatSessions();
  const handleDelete = useDeleteSessionAction((id) => {
    if (params.sessionId === id) router.push('/chat');
  });

  if (isLoading) {
    return (
      <Stack gap={6}>
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} h={40} radius="md" />
        ))}
      </Stack>
    );
  }

  if (isError) {
    return (
      <Text size="xs" c="var(--app-danger-text)" px="xs">
        Gagal memuat riwayat chat.
      </Text>
    );
  }

  if (!sessions?.length) {
    return (
      <Text size="xs" c="dimmed" px="xs">
        Belum ada percakapan.
      </Text>
    );
  }

  return (
    <Stack gap={2}>
      {sessions.map((session) => (
        <Group key={session.id} gap={0} wrap="nowrap" pos="relative">
          <NavLink
            component={Link}
            href={`/chat/${session.id}`}
            active={params.sessionId === session.id}
            variant="light"
            leftSection={<IconMessage size={16} aria-hidden />}
            label={
              <Text size="sm" truncate>
                {session.last_message_snippet || 'Percakapan baru'}
              </Text>
            }
            description={
              <Text size="xs" c="dimmed" truncate>
                {session.document_filename ?? 'Dokumen'}
              </Text>
            }
            pr={36}
          />
          <Box pos="absolute" right={4}>
            <Menu position="bottom-end" withinPortal>
              <Menu.Target>
                <ActionIcon size="sm" aria-label="Opsi sesi chat">
                  <IconDots size={16} aria-hidden />
                </ActionIcon>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item
                  color="red"
                  leftSection={<IconTrash size={14} aria-hidden />}
                  onClick={() => handleDelete(session.id)}
                >
                  Hapus
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Box>
        </Group>
      ))}
    </Stack>
  );
}
