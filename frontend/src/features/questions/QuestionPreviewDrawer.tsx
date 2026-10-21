'use client';

import Link from 'next/link';
import { Button, Divider, Drawer, Group, Stack, Text, Title } from '@mantine/core';
import { IconArrowRight } from '@tabler/icons-react';
import { BloomBadge, QuestionStatusBadge, QuestionTypeBadge } from '@/components/common/Badges';
import { CopyTextButton } from '@/components/common/CopyTextButton';
import { QualityWarningsAlert } from '@/components/common/QualityWarningsAlert';
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

          <QualityWarningsAlert warnings={question.quality_warnings} />

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

          <Button component={Link} href={`/questions/${question.id}`} variant="light" rightSection={<IconArrowRight size={16} aria-hidden />}>
            Buka detail &amp; audit
          </Button>
        </Stack>
      )}
    </Drawer>
  );
}
