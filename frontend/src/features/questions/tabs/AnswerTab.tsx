'use client';

import { Divider, Group, Paper, Stack, Text } from '@mantine/core';
import { CopyTextButton } from '@/components/common/CopyTextButton';
import type { QuestionDetail } from '@/types/question';
import { Section } from '../Section';

export function AnswerTab({ question }: { question: QuestionDetail }) {
  return (
    <Stack gap="lg">
      <Section title="Kunci jawaban">
        <Paper p="md" bg="var(--mantine-color-green-light)" withBorder={false}>
          <Group align="flex-start" wrap="nowrap" gap="xs">
            <Text size="sm" style={{ flex: 1 }}>
              {question.answer_key}
            </Text>
            <CopyTextButton value={question.answer_key} label="Salin kunci jawaban" />
          </Group>
        </Paper>
      </Section>

      {question.explanation && (
        <Section title="Penjelasan">
          <Text size="sm" lh={1.65}>
            {question.explanation}
          </Text>
        </Section>
      )}

      <Divider />

      <Group gap="xl" align="flex-start">
        {question.knowledge_point && (
          <Section title="Poin pengetahuan">
            <Text size="sm">{question.knowledge_point}</Text>
          </Section>
        )}
        {question.source_reference && (
          <Section title="Referensi materi">
            <Text size="sm">{question.source_reference}</Text>
          </Section>
        )}
      </Group>
    </Stack>
  );
}
