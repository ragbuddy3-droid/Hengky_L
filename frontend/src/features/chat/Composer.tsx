'use client';

import { ActionIcon, Box, Group, Paper, Text, Textarea, Tooltip } from '@mantine/core';
import { IconArrowUp } from '@tabler/icons-react';
import { ParamsPopover } from './ParamsPopover';
import { PromptChip } from './PromptChip';
import { EXAMPLE_PROMPTS } from './prompts';

export function Composer({
  value,
  onChange,
  onSend,
  documentId,
  sending,
  generating,
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: (text: string) => void;
  documentId?: string;
  sending: boolean;
  generating: boolean;
}) {
  const busy = sending || generating;
  const canSend = value.trim().length > 0 && !busy;
  const submit = () => canSend && onSend(value.trim());

  return (
    <Box px={{ base: 'md', sm: 'xl' }} pb="md" pt="xs" maw={960} mx="auto" w="100%">
      <Group gap={6} mb={8} wrap="wrap">
        <ParamsPopover documentId={documentId} disabled={busy} onSubmit={onSend} />
        {EXAMPLE_PROMPTS.map((p) => (
          <PromptChip key={p} visibleFrom="sm" onClick={() => onChange(p)} disabled={busy} c="dimmed">
            {p}
          </PromptChip>
        ))}
      </Group>
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
            placeholder={generating ? 'Menunggu soal selesai dibuat…' : 'Contoh: Buatkan 5 soal C3 bab 2'}
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
              color="teal"
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
