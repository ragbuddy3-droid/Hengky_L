'use client';

import Link from 'next/link';
import { Anchor, Badge, Blockquote, Card, Group, Spoiler, Stack, Text } from '@mantine/core';
import { CHUNK_CATEGORY_LABELS } from '@/lib/format';
import type { QuestionDetail } from '@/types/question';
import { Section } from '../Section';

export function SourcesTab({ question }: { question: QuestionDetail }) {
  const chunks = question.used_chunks ?? [];
  const documentId = chunks[0]?.document_id;

  return (
    <Stack gap="xl">
      {question.grounding_evidence && (
        <Section title="Bukti pendukung (grounding)">
          <Blockquote p="md" mt="xs">
            <Text size="sm" lh={1.65}>
              {question.grounding_evidence}
            </Text>
          </Blockquote>
        </Section>
      )}

      <Section title={`Potongan teks yang dipakai (${chunks.length})`}>
        {chunks.length === 0 ? (
          <Text size="sm" c="dimmed">
            Tidak ada data potongan teks untuk soal ini.
          </Text>
        ) : (
          <Stack gap="sm" mt="xs">
            {chunks.map((c, i) => (
              <Card key={c.id} padding="md">
                <Group justify="space-between" gap="xs" mb="xs">
                  <Group gap={6}>
                    <Text size="xs" fw={700} c="dimmed">
                      #{i + 1}
                    </Text>
                    {c.chapter && (
                      <Badge tt="none">
                        {c.chapter}
                      </Badge>
                    )}
                    {c.category && (
                      <Badge color="gray" variant="outline">
                        {CHUNK_CATEGORY_LABELS[c.category] ?? c.category}
                      </Badge>
                    )}
                  </Group>
                  {c.page_number != null && (
                    <Text size="xs" c="dimmed">
                      Hal. {c.page_number}
                    </Text>
                  )}
                </Group>
                {c.section_heading && (
                  <Text fw={600} size="sm" mb={4}>
                    {c.section_heading}
                  </Text>
                )}
                <Spoiler maxHeight={96} showLabel="Tampilkan semua" hideLabel="Sembunyikan">
                  <Text size="sm" lh={1.6} style={{ whiteSpace: 'pre-wrap' }}>
                    {c.text.trim()}
                  </Text>
                </Spoiler>
              </Card>
            ))}
            {documentId && (
              <Anchor component={Link} href={`/documents/${documentId}`} size="sm">
                Lihat semua potongan teks buku ini →
              </Anchor>
            )}
          </Stack>
        )}
      </Section>
    </Stack>
  );
}
