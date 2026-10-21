'use client';

import Link from 'next/link';
import { ActionIcon, Anchor, Box, Group, Paper, Text, Textarea, Tooltip } from '@mantine/core';
import { IconArrowUp } from '@tabler/icons-react';
import { GUEST_LIMIT_MESSAGES } from '@/components/common/GuestLimitTooltip';
import { useGuestQuota } from '@/hooks/useAuth';
import { ParamsPopover } from './ParamsPopover';
import { PromptChip } from './PromptChip';
import { EXAMPLE_PROMPTS, QUESTION_PROMPTS } from './prompts';

export function Composer({
  value,
  onChange,
  onSend,
  documentId,
  sending,
  generating,
  hasQuestions = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: (text: string) => void;
  documentId?: string;
  sending: boolean;
  generating: boolean;
  /** Sesi sudah punya soal: tampilkan contoh perintah bahas/buat ulang/revisi. */
  hasQuestions?: boolean;
}) {
  const { canGenerate } = useGuestQuota();
  const busy = sending || generating;
  const canSend = value.trim().length > 0 && !busy;
  const submit = () => canSend && onSend(value.trim());

  return (
    <Box px={{ base: 'md', sm: 'xl' }} pb="md" pt="xs" maw={960} mx="auto" w="100%">
      {canGenerate || hasQuestions ? (
        <Group gap={6} mb={8} wrap="wrap">
          {canGenerate && <ParamsPopover documentId={documentId} disabled={busy} onSubmit={onSend} />}
          {(hasQuestions ? QUESTION_PROMPTS : EXAMPLE_PROMPTS).map((p) => (
            <PromptChip key={p} visibleFrom="sm" onClick={() => onChange(p)} disabled={busy} c="dimmed">
              {p}
            </PromptChip>
          ))}
        </Group>
      ) : null}
      {!canGenerate && (
        <Text size="xs" c="dimmed" mb={8}>
          {GUEST_LIMIT_MESSAGES.generate}{' '}
          <Anchor component={Link} href="/login" fz="xs">
            Masuk
          </Anchor>
        </Text>
      )}
      <Paper p={6} radius="lg">
        <Group align="flex-end" gap="xs" wrap="nowrap">
          <Textarea
            value={value}
            onChange={(e) => onChange(e.currentTarget.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={
              generating
                ? 'Menunggu soal selesai dibuat…'
                : hasQuestions
                  ? 'Tanyakan, buat ulang, atau revisi soal, misalnya: Jelaskan soal nomor 2'
                  : canGenerate
                    ? 'Contoh: Buatkan 5 soal C3 bab 2'
                    : 'Tulis pesan'
            }
            aria-label="Tulis pesan"
            autosize
            minRows={1}
            maxRows={6}
            variant="unstyled"
            px="xs"
            style={{ flex: 1 }}
          />
          <Tooltip label="Kirim (Enter)">
            <ActionIcon
              size="lg"
              radius="xl"
              variant="filled"
              color="indigo"
              onClick={submit}
              disabled={!canSend}
              loading={sending}
              aria-label="Kirim pesan"
            >
              <IconArrowUp size={18} aria-hidden />
            </ActionIcon>
          </Tooltip>
        </Group>
      </Paper>
      <Text size="xs" c="dimmed" mt={6} ta="center">
        Enter untuk kirim · Shift+Enter untuk baris baru
      </Text>
    </Box>
  );
}
