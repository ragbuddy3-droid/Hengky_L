'use client';

import { Badge, Group, Progress, Stack, Table, Text } from '@mantine/core';
import { IconClipboardOff } from '@tabler/icons-react';
import { EmptyState } from '@/components/common/EmptyState';
import type { QuestionDetail } from '@/types/question';
import { Section } from '../Section';

const SCORE_COLORS = ['gray', 'blue', 'teal', 'green'];

export function RubricTab({ question }: { question: QuestionDetail }) {
  const rubric = [...(question.rubric ?? [])].sort((a, b) => b.score - a.score);
  const elements = question.answer_elements ?? [];
  const totalWeight = elements.reduce((sum, e) => sum + e.weight, 0);

  if (!rubric.length && !elements.length) {
    return (
      <EmptyState
        icon={<IconClipboardOff size={24} aria-hidden />}
        title="Tidak ada rubrik"
        description="Soal ini dinilai langsung dengan kunci jawaban, tanpa rubrik penskoran atau elemen jawaban."
      />
    );
  }

  return (
    <Stack gap="xl">
      {rubric.length > 0 && (
        <Section title="Rubrik penskoran">
          <Table withTableBorder verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={80}>Skor</Table.Th>
                <Table.Th>Kriteria</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rubric.map((r) => (
                <Table.Tr key={`${r.score}-${r.criteria}`}>
                  <Table.Td>
                    <Badge color={SCORE_COLORS[Math.min(r.score, SCORE_COLORS.length - 1)]} variant="filled">
                      {r.score}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{r.criteria}</Text>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Section>
      )}

      {elements.length > 0 && (
        <Section title="Elemen jawaban yang diharapkan">
          <Stack gap="sm">
            {elements.map((e) => {
              const pct = totalWeight ? Math.round((e.weight / totalWeight) * 100) : 0;
              return (
                <div key={e.element}>
                  <Group justify="space-between" gap="xs" mb={4} wrap="nowrap">
                    <Text size="sm">{e.element}</Text>
                    <Text size="xs" c="dimmed" style={{ flexShrink: 0 }}>
                      bobot {e.weight} · {pct}%
                    </Text>
                  </Group>
                  <Progress value={pct} size="sm" aria-label={`Bobot ${e.element}`} />
                </div>
              );
            })}
          </Stack>
        </Section>
      )}
    </Stack>
  );
}
