'use client';

import { Badge, Group, Paper, Stack, Table, Text, ThemeIcon, Timeline, Title } from '@mantine/core';
import { IconCheck, IconShieldOff, IconX } from '@tabler/icons-react';
import { EmptyState } from '@/components/common/EmptyState';
import type { QuestionDetail, ValidationLog } from '@/types/question';

const LAYER_LABELS: Record<string, string> = {
  pre_check: 'Pemeriksaan awal',
  grounding: 'Layer 1 · Grounding (kemiripan)',
  judge: 'Layer 2 · LLM-as-Judge',
};

const ASPECT_LABELS: Record<string, string> = {
  grounding: 'Kesesuaian dengan materi',
  bloom_adherence: 'Kesesuaian level Bloom',
  bahasa: 'Bahasa',
  answerability: 'Dapat dijawab',
  answer_alignment: 'Kesesuaian jawaban',
};

const isPass = (verdict: string) => /^pass|lolos|true/i.test(verdict.trim());

interface AspectResult {
  status?: string;
  score?: number | null;
  detected_level?: string | null;
  feedback?: string | null;
}

const isAspect = (v: unknown): v is AspectResult => typeof v === 'object' && v !== null && 'status' in v;

function AspectTable({ aspects }: { aspects: [string, AspectResult][] }) {
  return (
    <Table.ScrollContainer minWidth={520}>
      <Table withTableBorder verticalSpacing="xs" fz="sm">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Aspek</Table.Th>
            <Table.Th w={90}>Hasil</Table.Th>
            <Table.Th>Catatan juri</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {aspects.map(([key, a]) => {
            const pass = isPass(a.status ?? '');
            return (
              <Table.Tr key={key}>
                <Table.Td>
                  <Text size="sm" fw={500}>
                    {ASPECT_LABELS[key] ?? key}
                  </Text>
                  {(a.score != null || a.detected_level) && (
                    <Text size="xs" c="dimmed">
                      {a.score != null && `skor ${a.score}`}
                      {a.score != null && a.detected_level && ' · '}
                      {a.detected_level && `terdeteksi ${a.detected_level}`}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Badge color={pass ? 'green' : 'red'}>{pass ? 'Lolos' : 'Gagal'}</Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{a.feedback || '—'}</Text>
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

function Evaluations({ value }: { value: ValidationLog['aspect_evaluations'] }) {
  if (!value) return null;
  if (typeof value === 'string') return <Text size="sm">{value}</Text>;

  const entries = Object.entries(value);
  const aspects = entries.filter((e): e is [string, AspectResult] => isAspect(e[1]));
  const scalars = entries.filter(([, v]) => !isAspect(v) && (typeof v !== 'object' || v === null));

  return (
    <Stack gap="xs" mt="xs">
      {aspects.length > 0 && <AspectTable aspects={aspects} />}
      {scalars.length > 0 && (
        <Group gap="lg">
          {scalars.map(([k, v]) => (
            <Text key={k} size="xs" c="dimmed">
              {k.replaceAll('_', ' ')}:{' '}
              <Text span fw={600} c="var(--mantine-color-text)">
                {typeof v === 'number' ? v.toLocaleString('id-ID', { maximumFractionDigits: 3 }) : String(v)}
              </Text>
            </Text>
          ))}
        </Group>
      )}
    </Stack>
  );
}

export function ValidationTab({ question }: { question: QuestionDetail }) {
  const logs = question.validation_logs ?? [];

  if (!logs.length) {
    return (
      <EmptyState
        icon={<IconShieldOff size={24} aria-hidden />}
        title="Belum ada log validasi"
        description="Soal ini tidak memiliki catatan validasi."
      />
    );
  }

  const attempts = [...new Set(logs.map((l) => l.attempt_number))].sort((a, b) => a - b);

  return (
    <Stack gap="xl">
      <Text size="sm" c="dimmed">
        Setiap percobaan melewati Layer 1 (kemiripan dengan materi) lalu Layer 2 (penilaian LLM-as-Judge). Jika gagal, soal
        diperbaiki otomatis lalu divalidasi ulang.
      </Text>
      {attempts.map((attempt) => {
        const items = logs.filter((l) => l.attempt_number === attempt);
        return (
          <Stack key={attempt} gap="sm">
            <Title order={4} fz="sm">
              Percobaan {attempt}
              {attempt > 1 && (
                <Text span c="dimmed" fz="sm" fw={400}>
                  {' '}
                  · setelah perbaikan ke-{attempt - 1}
                </Text>
              )}
            </Title>
            <Timeline bulletSize={26} lineWidth={2}>
              {items.map((log) => {
                const pass = isPass(log.score_or_verdict);
                return (
                  <Timeline.Item
                    key={log.id}
                    bullet={
                      <ThemeIcon size={26} radius="xl" color={pass ? 'green.9' : 'red.8'}>
                        {pass ? <IconCheck size={14} aria-hidden /> : <IconX size={14} aria-hidden />}
                      </ThemeIcon>
                    }
                    title={
                      <Group gap="xs">
                        <Text fw={600} size="sm">
                          {LAYER_LABELS[log.layer] ?? log.layer}
                        </Text>
                        <Badge color={pass ? 'green' : 'red'} variant="light" tt="none">
                          {log.score_or_verdict}
                        </Badge>
                      </Group>
                    }
                  >
                    <Paper p="sm" mt="xs" withBorder={false} bg="var(--mantine-color-default-hover)">
                      {log.feedback && <Text size="sm">{log.feedback}</Text>}
                      <Evaluations value={log.aspect_evaluations} />
                    </Paper>
                  </Timeline.Item>
                );
              })}
            </Timeline>
          </Stack>
        );
      })}
    </Stack>
  );
}
