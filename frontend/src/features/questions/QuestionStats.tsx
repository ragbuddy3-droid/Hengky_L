'use client';

import { useMemo } from 'react';
import { Group, Paper, Progress, SimpleGrid, Stack, Text, Tooltip } from '@mantine/core';
import { BLOOM_COLORS, BLOOM_LEVELS, colorVar } from '@/theme/theme';
import { bloomCode, formatNumber } from '@/lib/format';
import type { Question } from '@/types/question';

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Paper p="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text fz={24} fw={700} mt={4}>
        {value}
      </Text>
      {hint && (
        <Text size="xs" c="dimmed">
          {hint}
        </Text>
      )}
    </Paper>
  );
}

export function QuestionStats({ questions }: { questions: Question[] }) {
  const stats = useMemo(() => {
    const total = questions.length;
    const final = questions.filter((q) => q.status === 'final').length;
    const refinements = questions.reduce((sum, q) => sum + q.refinement_count, 0);
    const byBloom = BLOOM_LEVELS.map((b) => ({
      ...b,
      count: questions.filter((q) => bloomCode(q.bloom_level) === b.value).length,
    })).filter((b) => b.count > 0);
    return { total, final, review: total - final, avgRefine: total ? refinements / total : 0, byBloom };
  }, [questions]);

  const pct = (n: number) => (stats.total ? Math.round((n / stats.total) * 100) : 0);

  return (
    <Stack gap="sm" mb="md">
      <SimpleGrid cols={{ base: 2, sm: 4 }}>
        <StatTile label="Total soal" value={formatNumber(stats.total)} />
        <StatTile label="Final" value={formatNumber(stats.final)} hint={`${pct(stats.final)}% lolos validasi`} />
        <StatTile label="Perlu tinjauan" value={formatNumber(stats.review)} hint={`${pct(stats.review)}% dari total`} />
        <StatTile
          label="Rata-rata perbaikan"
          value={stats.avgRefine.toLocaleString('id-ID', { maximumFractionDigits: 2 })}
          hint="putaran self-refinement per soal"
        />
      </SimpleGrid>

      {stats.byBloom.length > 0 && (
        <Paper p="md">
          <Text size="xs" c="dimmed" tt="uppercase" fw={600} mb="xs">
            Sebaran level Bloom
          </Text>
          <Progress.Root size={14} aria-label="Sebaran level Bloom">
            {stats.byBloom.map((b) => (
              <Tooltip key={b.value} label={`${b.label}: ${b.count} soal`}>
                <Progress.Section value={pct(b.count)} color={BLOOM_COLORS[b.value]} />
              </Tooltip>
            ))}
          </Progress.Root>
          <Group gap="md" mt="xs">
            {stats.byBloom.map((b) => (
              <Group key={b.value} gap={6}>
                <span
                  aria-hidden
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: 2,
                    background: colorVar(BLOOM_COLORS[b.value]),
                  }}
                />
                <Text size="xs">
                  {b.label} · <Text span fw={600}>{b.count}</Text>
                </Text>
              </Group>
            ))}
          </Group>
        </Paper>
      )}
    </Stack>
  );
}
