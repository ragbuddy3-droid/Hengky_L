'use client';

import { useEffect, useRef } from 'react';
import { Box, Group, Loader, Paper, Progress, ScrollArea, Skeleton, Spoiler, Stack, Text, ThemeIcon } from '@mantine/core';
import { IconSparkles } from '@tabler/icons-react';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import type { ChatMessage } from '@/types/chat';
import { EXAMPLE_PROMPTS } from './prompts';
import { PromptChip } from './PromptChip';
import type { GenerationProgress } from './useGenerationStream';

function AssistantAvatar() {
  return (
    <ThemeIcon size={32} radius="xl" variant="light" style={{ flexShrink: 0 }} aria-hidden>
      <IconSparkles size={18} />
    </ThemeIcon>
  );
}

function MessageBubble({
  message,
  pending,
  progress,
}: {
  message: ChatMessage;
  pending: boolean;
  progress: GenerationProgress | null;
}) {
  if (message.role === 'user') {
    return (
      <Group justify="flex-end">
        <Paper
          px="md"
          py="sm"
          maw="min(80%, 640px)"
          bg="var(--mantine-primary-color-light)"
          withBorder={false}
          style={{ borderRadius: 'var(--mantine-radius-lg) var(--mantine-radius-lg) var(--mantine-radius-xs) var(--mantine-radius-lg)' }}
        >
          <Text size="sm" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
            {message.content}
          </Text>
        </Paper>
      </Group>
    );
  }

  return (
    <Group align="flex-start" gap="sm" wrap="nowrap">
      <AssistantAvatar />
      <Paper px="md" py="sm" maw="min(90%, 760px)" miw={0} style={{ borderTopLeftRadius: 'var(--mantine-radius-xs)' }}>
        {pending ? (
          <Stack gap={6} miw={{ base: 220, sm: 320 }}>
            <Group gap="xs" wrap="nowrap">
              <Loader size="xs" type="dots" />
              <Text size="sm">{message.content}</Text>
            </Group>
            {progress ? (
              <>
                <Progress value={progress.percent} size="sm" animated aria-label="Progres pembuatan soal" />
                <Group justify="space-between" gap="xs">
                  <Text size="xs" c="dimmed">
                    {progress.phaseLabel}
                  </Text>
                  <Text size="xs" c="dimmed" ff="monospace">
                    {progress.finalCount}/{progress.target || '…'} lolos · {progress.percent}%
                  </Text>
                </Group>
              </>
            ) : (
              <Text size="xs" c="dimmed">
                Soal yang sudah jadi langsung muncul di panel &quot;Soal di sesi ini&quot;.
              </Text>
            )}
          </Stack>
        ) : (
          <Spoiler maxHeight={360} showLabel="Tampilkan semua" hideLabel="Ringkas">
            <MarkdownRenderer content={message.content} />
          </Spoiler>
        )}
      </Paper>
    </Group>
  );
}

function Welcome({ documentName, onPick }: { documentName?: string | null; onPick: (prompt: string) => void }) {
  return (
    <Stack align="center" ta="center" gap="xs" py="xl" maw={480} mx="auto">
      <ThemeIcon size={48} radius="xl" variant="light">
        <IconSparkles size={24} aria-hidden />
      </ThemeIcon>
      <Text fw={600} mt="xs">
        Siap membuat soal{documentName ? ` dari ${documentName}` : ''}
      </Text>
      <Text size="sm" c="dimmed">
        Sebutkan jumlah soal, level Bloom (C1–C4), dan bab bila perlu. Atau pilih salah satu contoh:
      </Text>
      <Group justify="center" gap={6} mt="xs">
        {EXAMPLE_PROMPTS.map((p) => (
          <PromptChip key={p} size="sm" onClick={() => onPick(p)}>
            {p}
          </PromptChip>
        ))}
      </Group>
    </Stack>
  );
}

export function MessageList({
  messages,
  isLoading,
  pendingMessageId,
  progress,
  documentName,
  onPickPrompt,
}: {
  messages: ChatMessage[] | undefined;
  isLoading: boolean;
  pendingMessageId: string | null;
  progress: GenerationProgress | null;
  documentName?: string | null;
  onPickPrompt: (prompt: string) => void;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const count = messages?.length ?? 0;

  useEffect(() => {
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: 'smooth' });
  }, [count]);

  return (
    <ScrollArea viewportRef={viewport} style={{ flex: 1 }} type="auto">
      <Box px={{ base: 'md', sm: 'xl' }} py="lg" maw={960} mx="auto">
        {isLoading ? (
          <Stack gap="md">
            <Skeleton h={44} w="40%" ml="auto" radius="lg" />
            <Skeleton h={120} w="70%" radius="lg" />
          </Stack>
        ) : count === 0 ? (
          <Welcome documentName={documentName} onPick={onPickPrompt} />
        ) : (
          <Stack gap="md" role="log" aria-live="polite" aria-label="Riwayat percakapan">
            {messages!.map((m) => (
              <MessageBubble key={m.id} message={m} pending={m.id === pendingMessageId} progress={progress} />
            ))}
          </Stack>
        )}
      </Box>
    </ScrollArea>
  );
}
