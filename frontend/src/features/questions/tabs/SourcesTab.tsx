'use client';

import Link from 'next/link';
import { Anchor, Blockquote, Stack, Text } from '@mantine/core';
import { ChunkCard } from '@/components/common/ChunkCard';
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
              <ChunkCard key={c.id} index={i + 1} chunk={c} meta={c.page_number != null ? `Hal. ${c.page_number}` : null}>
                <Text size="sm" lh={1.6} style={{ whiteSpace: 'pre-wrap' }}>
                  {c.text.trim()}
                </Text>
              </ChunkCard>
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
