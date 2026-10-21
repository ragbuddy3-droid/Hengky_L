'use client';

import { Box, Button, Tooltip, type ButtonProps } from '@mantine/core';
import { IconSparkles } from '@tabler/icons-react';
import { GuestLimitTooltip } from '@/components/common/GuestLimitTooltip';
import { useCreateSessionAction } from '@/features/chat/useCreateSessionAction';
import { useGuestQuota } from '@/hooks/useAuth';

/** Membuat sesi chat baru untuk dokumen lalu membuka halaman chat-nya. */
export function GenerateQuestionsButton({
  documentId,
  ready,
  ...props
}: { documentId: string; ready: boolean } & ButtonProps) {
  const createSession = useCreateSessionAction();
  const { canCreateSession } = useGuestQuota();

  const button = (
    <Button
      color="accent"
      leftSection={<IconSparkles size={16} aria-hidden />}
      disabled={!ready || !canCreateSession}
      loading={createSession.isPending}
      onClick={() => createSession.start(documentId)}
      {...props}
    >
      Buat Soal
    </Button>
  );

  if (!canCreateSession) {
    return (
      <GuestLimitTooltip kind="session" locked>
        {button}
      </GuestLimitTooltip>
    );
  }
  if (ready) return button;
  // Tombol disabled tidak memicu event mouse, jadi dibungkus span agar tooltip tetap muncul.
  return (
    <Tooltip label="Tunggu sampai buku selesai diproses">
      <Box component="span" display="inline-block">
        {button}
      </Box>
    </Tooltip>
  );
}
