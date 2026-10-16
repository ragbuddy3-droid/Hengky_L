'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ActionIcon, Alert, Anchor, Badge, Box, Button, Center, Drawer, Group, Menu, Text } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { IconBook2, IconClockExclamation, IconDots, IconListCheck, IconMessageOff, IconTrash } from '@tabler/icons-react';
import { confirmDelete } from '@/components/common/confirmDelete';
import { EmptyState } from '@/components/common/EmptyState';
import { QueryError } from '@/components/common/QueryError';
import { useDeleteSession, useSendMessage } from '@/hooks/useChat';
import { useQuestions } from '@/hooks/useQuestions';
import { ApiError } from '@/lib/api/client';
import { Composer } from './Composer';
import { MessageList } from './MessageList';
import { SessionQuestionsPanel } from './SessionQuestionsPanel';
import { useSessionGeneration } from './useSessionGeneration';

const PANEL_WIDTH = 380;
const FULL_HEIGHT = { base: 'calc(100dvh - 56px)', sm: '100dvh' };

export function ChatSessionView({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const [draft, setDraft] = useState('');
  const [panelOpened, panel] = useDisclosure(false);

  const { sessionQuery, messagesQuery, pending, unreachable } = useSessionGeneration(sessionId);
  const session = sessionQuery.data;
  const sendMessage = useSendMessage(sessionId);
  const deleteSession = useDeleteSession();
  const questionCount = useQuestions(sessionId).data?.length ?? 0;

  const send = (text: string) => {
    setDraft('');
    sendMessage.mutate(text, {
      onError: (err) => {
        setDraft(text);
        notifications.show({ color: 'red', title: 'Pesan gagal dikirim', message: err.message });
      },
    });
  };

  const handleDelete = () =>
    confirmDelete({
      title: 'Hapus sesi chat?',
      message: 'Riwayat percakapan sesi ini akan dihapus.',
      onConfirm: () =>
        deleteSession.mutate(sessionId, {
          onSuccess: () => router.push('/chat'),
          onError: (err) => notifications.show({ color: 'red', title: 'Gagal menghapus', message: err.message }),
        }),
    });

  if (sessionQuery.error instanceof ApiError && sessionQuery.error.status === 404) {
    return (
      <Center h={FULL_HEIGHT} p="md">
        <EmptyState
          icon={<IconMessageOff size={24} aria-hidden />}
          title="Sesi chat tidak ditemukan"
          description="Sesi ini mungkin sudah dihapus."
          action={
            <Button component={Link} href="/chat">
              Mulai chat baru
            </Button>
          }
        />
      </Center>
    );
  }

  const pendingCount = pending?.count ?? 0;
  const panelContent = <SessionQuestionsPanel sessionId={sessionId} pendingCount={pendingCount} documentName={session?.document_filename} />;

  return (
    <Box h={FULL_HEIGHT} display="flex">
      <Box style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <Group
          justify="space-between"
          px={{ base: 'md', sm: 'xl' }}
          py="sm"
          wrap="nowrap"
          style={{ borderBottom: '1px solid var(--mantine-color-default-border)' }}
        >
          <Group gap="xs" wrap="nowrap" miw={0}>
            <IconBook2 size={18} aria-hidden style={{ flexShrink: 0 }} />
            {session ? (
              <Anchor component={Link} href={`/dokumen/${session.document_id}`} fw={600} c="inherit" truncate>
                {session.document_filename ?? 'Dokumen'}
              </Anchor>
            ) : (
              <Text fw={600} c="dimmed">
                Memuat…
              </Text>
            )}
          </Group>
          <Group gap={4} wrap="nowrap">
            <Button
              hiddenFrom="md"
              variant="default"
              size="xs"
              leftSection={<IconListCheck size={14} aria-hidden />}
              rightSection={questionCount || pendingCount ? <Badge size="xs" px={6}>{questionCount || '…'}</Badge> : null}
              onClick={panel.open}
            >
              Soal
            </Button>
            <Menu position="bottom-end">
              <Menu.Target>
                <ActionIcon aria-label="Opsi sesi">
                  <IconDots size={18} aria-hidden />
                </ActionIcon>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item color="red" leftSection={<IconTrash size={14} aria-hidden />} onClick={handleDelete}>
                  Hapus sesi
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>

        {messagesQuery.error ? (
          <Box p="xl">
            <QueryError error={messagesQuery.error} onRetry={() => messagesQuery.refetch()} />
          </Box>
        ) : (
          <MessageList
            messages={messagesQuery.data}
            isLoading={messagesQuery.isLoading}
            pendingMessageId={pending?.messageId ?? null}
            documentName={session?.document_filename}
            onPickPrompt={setDraft}
          />
        )}

        {unreachable && (
          <Box px={{ base: 'md', sm: 'xl' }} maw={960} mx="auto" w="100%">
            <Alert color="orange" icon={<IconClockExclamation size={18} aria-hidden />} title="Server tidak merespons">
              Soal sedang dibuat, tetapi server tidak bisa dihubungi. Periksa apakah backend masih berjalan, lalu{' '}
              <Anchor component="button" onClick={() => sessionQuery.refetch()} fz="sm">
                cek lagi
              </Anchor>
              .
            </Alert>
          </Box>
        )}

        <Composer
          value={draft}
          onChange={setDraft}
          onSend={send}
          documentId={session?.document_id}
          sending={sendMessage.isPending}
          generating={!!pending}
        />
      </Box>

      <Box
        visibleFrom="md"
        w={PANEL_WIDTH}
        style={{ flexShrink: 0, borderLeft: '1px solid var(--mantine-color-default-border)' }}
        bg="var(--mantine-color-body)"
      >
        {panelContent}
      </Box>

      <Drawer opened={panelOpened} onClose={panel.close} position="right" size="md" withCloseButton title="Soal" hiddenFrom="md" padding={0}>
        {panelContent}
      </Drawer>
    </Box>
  );
}
