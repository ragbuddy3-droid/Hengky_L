'use client';

import { Accordion, Badge, Code, Group, ScrollArea, SegmentedControl, Stack, Text } from '@mantine/core';
import { useState } from 'react';
import { IconTerminal2 } from '@tabler/icons-react';
import { CopyTextButton } from '@/components/common/CopyTextButton';
import { EmptyState } from '@/components/common/EmptyState';
import { formatNumber } from '@/lib/format';
import type { PromptTraceItem, QuestionDetail } from '@/types/question';

type View = 'parsed' | 'prompt' | 'raw';

const formatSeconds = (ms: number) => `${(ms / 1000).toLocaleString('id-ID', { maximumFractionDigits: 1 })} dtk`;

function TraceBody({ trace }: { trace: PromptTraceItem }) {
  const [view, setView] = useState<View>(trace.parsed_output ? 'parsed' : 'prompt');
  const content =
    view === 'parsed'
      ? JSON.stringify(trace.parsed_output, null, 2)
      : view === 'prompt'
        ? trace.prompt_sent
        : trace.raw_response;

  return (
    <Stack gap="xs">
      {trace.error_message && (
        <Text size="sm" c="var(--app-danger-text)">
          {trace.error_message}
        </Text>
      )}
      <Group justify="space-between" gap="xs">
        <SegmentedControl
          size="xs"
          value={view}
          onChange={(v) => setView(v as View)}
          data={[
            { value: 'parsed', label: 'Output terstruktur', disabled: !trace.parsed_output },
            { value: 'prompt', label: 'Prompt' },
            { value: 'raw', label: 'Respons mentah' },
          ]}
        />
        <Group gap={4}>
          <Text size="xs" c="dimmed">
            {formatNumber(content.length)} karakter
          </Text>
          <CopyTextButton value={content} label="Salin isi" />
        </Group>
      </Group>
      <ScrollArea.Autosize mah={420} type="auto">
        <Code block fz="xs" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {content}
        </Code>
      </ScrollArea.Autosize>
    </Stack>
  );
}

export function TracesTab({ question }: { question: QuestionDetail }) {
  const traces = [...(question.prompt_traces ?? [])].sort(
    (a, b) => a.step_number - b.step_number || a.attempt_number - b.attempt_number,
  );

  if (!traces.length) {
    return (
      <EmptyState
        icon={<IconTerminal2 size={24} aria-hidden />}
        title="Tidak ada jejak prompt"
        description="Jejak tahapan pembuatan tidak tersimpan untuk soal ini."
      />
    );
  }

  const totalMs = traces.reduce((sum, t) => sum + t.latency_ms, 0);

  return (
    <Stack gap="md">
      <Text size="sm" c="dimmed">
        {traces.length} pemanggilan LLM · total {formatSeconds(totalMs)}. Buka sebuah tahap untuk melihat prompt, respons
        mentah, dan hasil yang sudah diurai.
      </Text>
      <Accordion variant="separated" radius="md" chevronPosition="left">
        {traces.map((t, i) => {
          const ok = t.status === 'success';
          return (
            <Accordion.Item key={`${t.step_number}-${t.attempt_number}-${i}`} value={String(i)}>
              <Accordion.Control>
                <Group justify="space-between" gap="xs" wrap="nowrap">
                  <Text size="sm" fw={500} truncate>
                    {t.stage_name}
                  </Text>
                  <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
                    {t.attempt_number > 1 && <Badge color="violet">percobaan {t.attempt_number}</Badge>}
                    <Badge color="gray" variant="outline">
                      {formatSeconds(t.latency_ms)}
                    </Badge>
                    <Badge color={ok ? 'green' : 'red'}>{ok ? 'Sukses' : t.status}</Badge>
                  </Group>
                </Group>
              </Accordion.Control>
              <Accordion.Panel>
                <TraceBody trace={t} />
              </Accordion.Panel>
            </Accordion.Item>
          );
        })}
      </Accordion>
    </Stack>
  );
}
