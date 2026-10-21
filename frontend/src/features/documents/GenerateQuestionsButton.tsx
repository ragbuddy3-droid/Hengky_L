'use client';

import { useRouter } from 'next/navigation';
import { Button, Tooltip, type ButtonProps } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconSparkles } from '@tabler/icons-react';
import { GUEST_LIMIT_MESSAGES } from '@/components/common/GuestLimitTooltip';
import { useGuestQuota } from '@/hooks/useAuth';
import { useCreateSession } from '@/hooks/useChat';

/** Membuat sesi chat baru untuk dokumen lalu membuka halaman chat-nya. */
export function GenerateQuestionsButton({
  documentId,
  ready,
  ...props
}: { documentId: string; ready: boolean } & ButtonProps) {
  const router = useRouter();
  const createSession = useCreateSession();
  const { canCreateSession } = useGuestQuota();

  const button = (
    <Button
      color="accent"
      leftSection={<IconSparkles size={16} aria-hidden />}
      disabled={!ready || !canCreateSession}
      loading={createSession.isPending}
      onClick={() =>
        createSession.mutate(documentId, {
          onSuccess: (session) => router.push(`/chat/${session.id}`),
          onError: (err) => notifications.show({ color: 'red', title: 'Gagal membuat sesi', message: err.message }),
        })
      }
      {...props}
    >
      Buat Soal
    </Button>
  );

  if (!canCreateSession) {
    return (
      <Tooltip label={GUEST_LIMIT_MESSAGES.session} multiline w={260}>
        {button}
      </Tooltip>
    );
  }
  return ready ? button : <Tooltip label="Tunggu sampai buku selesai diproses">{button}</Tooltip>;
}
