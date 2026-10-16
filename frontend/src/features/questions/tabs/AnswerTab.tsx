'use client';

import { Divider, Group, List, Paper, Stack, Text } from '@mantine/core';
import { CopyTextButton } from '@/components/common/CopyTextButton';
import type { QuestionDetail, QuestionOption } from '@/types/question';
import { Section } from '../Section';

/** Opsi detail bisa berupa list {label,text} atau dict {A: "..."}; seragamkan. */
function normalizeOptions(options: QuestionDetail['options']): QuestionOption[] {
  if (!options) return [];
  if (Array.isArray(options)) {
    return options
      .filter((o): o is QuestionOption => typeof o === 'object' && o !== null && 'label' in o && 'text' in o)
      .map((o) => ({ label: String(o.label), text: String(o.text) }));
  }
  return Object.entries(options).map(([label, text]) => ({ label, text: String(text) }));
}

export function AnswerTab({ question }: { question: QuestionDetail }) {
  const options = normalizeOptions(question.options);

  return (
    <Stack gap="lg">
      {options.length > 0 && (
        <Section title="Pilihan jawaban">
          <List spacing={4} size="sm">
            {options.map((o) => (
              <List.Item key={o.label}>
                <Text span fw={600}>
                  {o.label}.
                </Text>{' '}
                {o.text}
              </List.Item>
            ))}
          </List>
        </Section>
      )}

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
