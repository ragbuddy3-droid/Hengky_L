'use client';

import { useState } from 'react';
import { Badge, Group, Loader, Paper, ScrollArea, Skeleton, Stack, Text, UnstyledButton } from '@mantine/core';
import { IconListCheck } from '@tabler/icons-react';
import { BloomBadge, QuestionStatusBadge } from '@/components/common/Badges';
import { QueryError } from '@/components/common/QueryError';
import { ExportMenu } from '@/features/questions/ExportMenu';
import { QuestionPreviewDrawer } from '@/features/questions/QuestionPreviewDrawer';
import { useQuestions } from '@/hooks/useQuestions';
import { QUESTION_TYPE_LABELS } from '@/lib/format';
import type { Question } from '@/types/question';

function QuestionRow({ question, index, onSelect }: { question: Question; index: number; onSelect: () => void }) {
  return (
    <UnstyledButton onClick={onSelect} w="100%" aria-label={`Lihat soal ${index}`}>
      <Paper p="sm" className="hover-surface">
        <Group justify="space-between" mb={6} gap={6}>
          <Group gap={6}>
            <Text size="xs" fw={700} c="dimmed">
              #{index}
            </Text>
            <BloomBadge level={question.bloom_level} size="xs" />
            <Text size="xs" c="dimmed">
              {QUESTION_TYPE_LABELS[question.question_type] ?? question.question_type}
            </Text>
          </Group>
          <QuestionStatusBadge status={question.status} />
        </Group>
        <Text size="sm" lineClamp={3}>
          {question.question_text}
        </Text>
      </Paper>
    </UnstyledButton>
  );
}

export function SessionQuestionsPanel({
  sessionId,
  pendingCount,
  documentName,
}: {
  sessionId: string;
  pendingCount: number;
  documentName?: string | null;
}) {
  const { data, isLoading, error, refetch } = useQuestions(sessionId);
  const [selected, setSelected] = useState<Question | null>(null);
  // Urutan dari API sudah sama dengan penomoran di pesan ringkasan chat.
  const questions = data ?? [];
  const finalCount = questions.filter((q) => q.status === 'final').length;
  const title = documentName ? `Soal ${documentName.replace(/\.pdf$/i, '')}` : 'Soal sesi chat';

  return (
    <Stack gap={0} h="100%">
      <Group justify="space-between" px="md" py="sm" style={{ borderBottom: '1px solid var(--mantine-color-default-border)' }}>
        <Group gap="xs">
          <IconListCheck size={18} aria-hidden />
          <Text fw={600}>Soal di sesi ini</Text>
        </Group>
        {questions.length > 0 && (
          <Group gap={4}>
            <Badge color="gray">{questions.length}</Badge>
            <ExportMenu questions={questions} title={title} compact />
          </Group>
        )}
      </Group>

      {questions.length > 0 && (
        <Group gap="md" px="md" py="xs">
          <Text size="xs" c="dimmed">
            <Text span fw={600} c="var(--app-success-text)">
              {finalCount}
            </Text>{' '}
            final
          </Text>
          <Text size="xs" c="dimmed">
            <Text span fw={600} c="var(--app-warning-text)">
              {questions.length - finalCount}
            </Text>{' '}
            perlu tinjauan
          </Text>
        </Group>
      )}

      <ScrollArea style={{ flex: 1 }} type="auto">
        <Stack gap="xs" p="md">
          {pendingCount > 0 && (
            <Paper p="sm" bg="var(--mantine-primary-color-light)" withBorder={false}>
              <Group gap="xs" wrap="nowrap">
                <Loader size="xs" />
                <Text size="sm">Membuat {pendingCount} soal…</Text>
              </Group>
            </Paper>
          )}
          {pendingCount > 0 &&
            Array.from({ length: Math.min(pendingCount, 3) }, (_, i) => <Skeleton key={i} h={84} radius="md" />)}

          {isLoading ? (
            Array.from({ length: 3 }, (_, i) => <Skeleton key={i} h={84} radius="md" />)
          ) : error ? (
            <QueryError error={error} onRetry={() => refetch()} />
          ) : questions.length === 0 && pendingCount === 0 ? (
            <Text size="sm" c="dimmed" ta="center" py="xl">
              Soal yang dibuat di percakapan ini akan muncul di sini.
            </Text>
          ) : (
            questions.map((q, i) => <QuestionRow key={q.id} question={q} index={i + 1} onSelect={() => setSelected(q)} />)
          )}
        </Stack>
      </ScrollArea>

      <QuestionPreviewDrawer question={selected} onClose={() => setSelected(null)} />
    </Stack>
  );
}
