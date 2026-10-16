'use client';

import Link from 'next/link';
import { Alert, Button, Divider, Drawer, Group, List, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle, IconArrowRight } from '@tabler/icons-react';
import { BloomBadge, QuestionStatusBadge, QuestionTypeBadge } from '@/components/common/Badges';
import { CopyTextButton } from '@/components/common/CopyTextButton';
import type { Question } from '@/types/question';
import { Section } from './Section';

export function QuestionPreviewDrawer({ question, onClose }: { question: Question | null; onClose: () => void }) {
  return (
    <Drawer
      opened={!!question}
      onClose={onClose}
      position="right"
      size="lg"
      title={<Text fw={600}>Pratinjau Soal</Text>}
    >
      {question && (
        <Stack gap="md">
          <Group gap={6}>
            <QuestionTypeBadge type={question.question_type} />
            <BloomBadge level={question.bloom_level} />
            <QuestionStatusBadge status={question.status} />
            {question.refinement_count > 0 && (
              <Text size="xs" c="dimmed">
                {question.refinement_count}× perbaikan
              </Text>
            )}
          </Group>

          <Group align="flex-start" wrap="nowrap" gap="xs">
            <Title order={3} fz="md" lh={1.5} fw={600} style={{ flex: 1 }}>
              {question.question_text}
            </Title>
            <CopyTextButton value={question.question_text} label="Salin soal" />
          </Group>

          {!!question.quality_warnings?.length && (
            <Alert color="orange" variant="light" icon={<IconAlertTriangle size={18} aria-hidden />} title="Catatan kualitas">
              <List size="sm">
                {question.quality_warnings.map((w) => (
                  <List.Item key={w}>{w}</List.Item>
                ))}
              </List>
            </Alert>
          )}

          {!!question.options?.length && (
            <Section title="Pilihan">
              <List size="sm" spacing={4}>
                {question.options.map((o) => (
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

          <Divider />

          <Section title="Kunci jawaban">
            <Text size="sm">{question.answer_key}</Text>
          </Section>

          {question.explanation && (
            <Section title="Penjelasan">
              <Text size="sm" c="dimmed">
                {question.explanation}
              </Text>
            </Section>
          )}

          {question.source_reference && (
            <Section title="Referensi materi">
              <Text size="sm" ff="monospace">
                {question.source_reference}
              </Text>
            </Section>
          )}

          <Button component={Link} href={`/soal/${question.id}`} variant="light" rightSection={<IconArrowRight size={16} aria-hidden />}>
            Buka detail &amp; audit
          </Button>
        </Stack>
      )}
    </Drawer>
  );
}
