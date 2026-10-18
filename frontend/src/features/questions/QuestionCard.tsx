'use client';

import Link from 'next/link';
import { Anchor, Group, Paper, Text } from '@mantine/core';
import { IconAlertTriangle, IconRefresh } from '@tabler/icons-react';
import { BloomBadge, QuestionStatusBadge, QuestionTypeBadge } from '@/components/common/Badges';
import type { Question } from '@/types/question';

export function QuestionCard({ question }: { question: Question }) {
  const warnings = question.quality_warnings?.length ?? 0;

  return (
    <Anchor component={Link} href={`/questions/${question.id}`} underline="never" c="inherit" display="block">
      <Paper p="md" className="hover-surface">
        <Group justify="space-between" gap="xs" mb="xs">
          <Group gap={6}>
            <QuestionTypeBadge type={question.question_type} />
            <BloomBadge level={question.bloom_level} />
            {question.refinement_count > 0 && (
              <Group gap={2} c="dimmed">
                <IconRefresh size={12} aria-hidden />
                <Text size="xs">{question.refinement_count}× perbaikan</Text>
              </Group>
            )}
            {warnings > 0 && (
              <Group gap={2} c="var(--app-warning-text)">
                <IconAlertTriangle size={12} aria-hidden />
                <Text size="xs">{warnings} catatan</Text>
              </Group>
            )}
          </Group>
          <QuestionStatusBadge status={question.status} />
        </Group>
        <Text fw={500} lineClamp={2}>
          {question.question_text}
        </Text>
        {question.source_reference && (
          <Text size="xs" c="dimmed" mt={6} truncate>
            {question.source_reference}
          </Text>
        )}
      </Paper>
    </Anchor>
  );
}
