'use client';

import { useState } from 'react';
import { Badge, Group, Loader, Paper, Progress, ScrollArea, Skeleton, Stack, Text, UnstyledButton } from '@mantine/core';
import { IconListCheck } from '@tabler/icons-react';
import { BloomBadge, QuestionStatusBadge } from '@/components/common/Badges';
import { QueryError } from '@/components/common/QueryError';
import { ExportMenu } from '@/features/questions/ExportMenu';
import { QuestionPreviewDrawer } from '@/features/questions/QuestionPreviewDrawer';
import { useQuestions } from '@/hooks/useQuestions';
import { QUESTION_STATUS_LABELS, QUESTION_TYPE_LABELS } from '@/lib/format';
import type { CandidateStatus } from '@/types/chat';
import type { Question } from '@/types/question';
import type { GenerationProgress, StreamCandidate } from './useGenerationStream';

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
          <Group gap={4}>
            {question.revision_count > 0 && (
              <Badge size="xs" variant="light" color="gray">
                direvisi {question.revision_count}×
              </Badge>
            )}
            <QuestionStatusBadge status={question.status} />
          </Group>
        </Group>
        <Text size="sm" lineClamp={3}>
          {question.question_text}
        </Text>
      </Paper>
    </UnstyledButton>
  );
}

const CANDIDATE_STATUS: Record<CandidateStatus, { color: string; label: string; busy: boolean }> = {
  blueprint: { color: 'gray', label: 'Merancang', busy: true },
  writing: { color: 'blue', label: 'Menulis', busy: true },
  validating: { color: 'cyan', label: 'Memvalidasi', busy: true },
  refining: { color: 'yellow', label: 'Memperbaiki', busy: true },
  final: { color: 'green', label: 'Lolos', busy: false },
  needs_review: { color: 'orange', label: QUESTION_STATUS_LABELS.needs_review, busy: false },
  dropped: { color: 'gray', label: 'Dibatalkan', busy: false },
};

/** Soal yang sedang dibuat, tampil begitu Stage 4 menghasilkan teksnya lalu diperbarui sampai lolos validasi. */
function CandidateRow({ candidate }: { candidate: StreamCandidate }) {
  const meta = CANDIDATE_STATUS[candidate.status];
  const text = candidate.question?.question;
  const label = candidate.status === 'refining' && candidate.attempt ? `${meta.label} (${candidate.attempt})` : meta.label;
  return (
    <Paper p="sm" className="stream-in" style={{ opacity: meta.busy ? 0.85 : 1 }}>
      <Group justify="space-between" mb={6} gap={6}>
        <Group gap={6}>
          {candidate.question?.bloom_level && <BloomBadge level={candidate.question.bloom_level} size="xs" />}
          {candidate.question?.question_type && (
            <Text size="xs" c="dimmed">
              {QUESTION_TYPE_LABELS[candidate.question.question_type] ?? candidate.question.question_type}
            </Text>
          )}
        </Group>
        <Badge
          color={meta.color}
          variant={meta.busy ? 'light' : 'dot'}
          leftSection={meta.busy ? <Loader size={10} color={meta.color} /> : undefined}
        >
          {label}
        </Badge>
      </Group>
      {text ? (
        <Text size="sm" lineClamp={3}>
          {text}
        </Text>
      ) : (
        <Stack gap={6}>
          <Skeleton h={10} radius="sm" />
          <Skeleton h={10} w="70%" radius="sm" />
        </Stack>
      )}
    </Paper>
  );
}

function GenerationProgressBlock({ progress, pendingCount }: { progress: GenerationProgress | null; pendingCount: number }) {
  const target = progress?.target || pendingCount;
  return (
    <Paper p="sm" bg="var(--mantine-primary-color-light)" withBorder={false}>
      <Group justify="space-between" gap="xs" wrap="nowrap" mb={8}>
        <Group gap="xs" wrap="nowrap" miw={0}>
          <Loader size="xs" />
          <Text size="sm" truncate>
            {progress?.phaseLabel ?? `Membuat ${pendingCount} soal…`}
          </Text>
        </Group>
        <Text size="xs" fw={600} ff="monospace" style={{ flexShrink: 0 }}>
          {progress?.finalCount ?? 0}/{target} lolos
        </Text>
      </Group>
      <Progress value={progress?.percent ?? 2} size="sm" animated aria-label="Progres pembuatan soal" />
    </Paper>
  );
}

export function SessionQuestionsPanel({
  sessionId,
  pendingCount,
  progress,
  documentName,
}: {
  sessionId: string;
  pendingCount: number;
  progress: GenerationProgress | null;
  documentName?: string | null;
}) {
  const { data, isLoading, error, refetch } = useQuestions(sessionId);
  const [selected, setSelected] = useState<Question | null>(null);
  const questions = data ?? [];
  const finalCount = questions.filter((q) => q.status === 'final').length;
  const generating = pendingCount > 0 || progress !== null;
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
          {generating && <GenerationProgressBlock progress={progress} pendingCount={pendingCount} />}
          {generating &&
            (progress?.candidates.length
              ? progress.candidates.map((c) => <CandidateRow key={c.id} candidate={c} />)
              : Array.from({ length: Math.min(pendingCount, 3) }, (_, i) => <Skeleton key={i} h={84} radius="md" />))}
          {generating && questions.length > 0 && (
            <Text size="xs" c="dimmed" fw={600} mt="xs">
              Soal sebelumnya
            </Text>
          )}

          {isLoading ? (
            Array.from({ length: 3 }, (_, i) => <Skeleton key={i} h={84} radius="md" />)
          ) : error ? (
            <QueryError error={error} onRetry={() => refetch()} />
          ) : questions.length === 0 && !generating ? (
            <Text size="sm" c="dimmed" ta="center" py="xl">
              Soal yang dibuat di percakapan ini akan muncul di sini.
            </Text>
          ) : (
            // API mengurutkan terbaru dulu; nomor mengikuti urutan pembuatan, sama dengan "soal nomor N" di chat
            questions.map((q, i) => (
              <QuestionRow key={q.id} question={q} index={questions.length - i} onSelect={() => setSelected(q)} />
            ))
          )}
        </Stack>
      </ScrollArea>

      <QuestionPreviewDrawer question={selected} onClose={() => setSelected(null)} />
    </Stack>
  );
}
