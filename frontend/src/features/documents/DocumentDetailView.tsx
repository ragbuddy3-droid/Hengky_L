'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Alert, Anchor, Breadcrumbs, Button, Group, Paper, SimpleGrid, Skeleton, Stack, Text, Title } from '@mantine/core';
import { IconAlertCircle, IconFileOff, IconLoader, IconTrash } from '@tabler/icons-react';
import { DocumentStatusBadge } from '@/components/common/Badges';
import { EmptyState } from '@/components/common/EmptyState';
import { PageContainer } from '@/components/common/PageContainer';
import { QueryError } from '@/components/common/QueryError';
import { useDocument, useDocumentChunks } from '@/hooks/useDocuments';
import { ApiError } from '@/lib/api/client';
import { formatDate, formatNumber } from '@/lib/format';
import type { DocumentChunk } from '@/types/document';
import { ChunkList } from './ChunkList';
import { GenerateQuestionsButton } from './GenerateQuestionsButton';
import { useDeleteDocumentAction } from './useDeleteDocumentAction';

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <Paper p="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text fz={24} fw={700} mt={4}>
        {value}
      </Text>
    </Paper>
  );
}

function ChunkStats({ chunks }: { chunks: DocumentChunk[] }) {
  const stats = useMemo(() => {
    const words = chunks.reduce((sum, c) => sum + c.word_count, 0);
    const chapters = new Set(chunks.map((c) => c.chapter).filter(Boolean)).size;
    return { words, chapters, avg: chunks.length ? Math.round(words / chunks.length) : 0 };
  }, [chunks]);

  return (
    <SimpleGrid cols={{ base: 2, sm: 4 }}>
      <StatTile label="Potongan teks" value={formatNumber(chunks.length)} />
      <StatTile label="Bab terdeteksi" value={formatNumber(stats.chapters)} />
      <StatTile label="Total kata" value={formatNumber(stats.words)} />
      <StatTile label="Rata-rata kata" value={formatNumber(stats.avg)} />
    </SimpleGrid>
  );
}

export function DocumentDetailView({ id }: { id: string }) {
  const router = useRouter();
  const { data: doc, isLoading, error, refetch } = useDocument(id);
  const ready = doc?.status === 'ready';
  const chunksQuery = useDocumentChunks(id, ready);
  const handleDelete = useDeleteDocumentAction(() => router.push('/dokumen'));

  const breadcrumbs = (
    <Breadcrumbs mb="md" fz="sm" separator={<Text span c="dimmed" aria-hidden>/</Text>}>
      <Anchor component={Link} href="/dokumen">
        Dokumen
      </Anchor>
      <Text size="sm" c="dimmed" truncate maw={280}>
        {doc?.filename ?? '…'}
      </Text>
    </Breadcrumbs>
  );

  if (isLoading) {
    return (
      <PageContainer>
        {breadcrumbs}
        <Skeleton h={36} w="50%" mb="xs" />
        <Skeleton h={18} w="30%" mb="xl" />
        <Skeleton h={88} radius="md" />
      </PageContainer>
    );
  }

  if (error) {
    return (
      <PageContainer>
        {breadcrumbs}
        {error instanceof ApiError && error.status === 404 ? (
          <EmptyState
            icon={<IconFileOff size={24} aria-hidden />}
            title="Dokumen tidak ditemukan"
            description="Buku ini mungkin sudah dihapus."
            action={
              <Button component={Link} href="/dokumen" variant="default">
                Kembali ke daftar dokumen
              </Button>
            }
          />
        ) : (
          <QueryError error={error} onRetry={() => refetch()} />
        )}
      </PageContainer>
    );
  }

  if (!doc) return null;

  return (
    <PageContainer>
      {breadcrumbs}
      <Group justify="space-between" align="flex-start" mb="lg" gap="md">
        <Stack gap={4} miw={0} style={{ flex: '1 1 320px' }}>
          <Title order={2} fz={{ base: 22, sm: 26 }} style={{ overflowWrap: 'anywhere' }}>
            {doc.filename}
          </Title>
          <Group gap="xs">
            <DocumentStatusBadge status={doc.status} />
            <Text size="sm" c="dimmed">
              {doc.subject}
              {doc.created_at && ` · diunggah ${formatDate(doc.created_at)}`}
            </Text>
          </Group>
        </Stack>
        <Group gap="sm">
          <Button
            variant="default"
            color="red"
            leftSection={<IconTrash size={16} aria-hidden />}
            onClick={() => handleDelete(doc)}
          >
            Hapus
          </Button>
          <GenerateQuestionsButton documentId={doc.id} ready={ready} />
        </Group>
      </Group>

      {doc.status === 'failed' && (
        <Alert color="red" title="Pemrosesan gagal" icon={<IconAlertCircle size={18} aria-hidden />} mb="lg">
          {doc.error_message || 'Terjadi kesalahan saat memproses buku. Coba hapus lalu unggah ulang.'}
        </Alert>
      )}

      {(doc.status === 'pending' || doc.status === 'processing') && (
        <Alert color="blue" title="Sedang diproses" icon={<IconLoader size={18} aria-hidden />} mb="lg">
          Buku sedang diekstrak dan dipotong menjadi bagian-bagian kecil. Halaman ini akan diperbarui otomatis.
        </Alert>
      )}

      {ready && (
        <Stack gap="lg">
          {chunksQuery.error ? (
            <QueryError error={chunksQuery.error} onRetry={() => chunksQuery.refetch()} title="Gagal memuat potongan teks" />
          ) : (
            <>
              {chunksQuery.data ? <ChunkStats chunks={chunksQuery.data} /> : <Skeleton h={88} radius="md" />}
              <div>
                <Title order={3} fz="lg" mb="sm">
                  Potongan Teks
                </Title>
                <ChunkList chunks={chunksQuery.data} isLoading={chunksQuery.isLoading} />
              </div>
            </>
          )}
        </Stack>
      )}
    </PageContainer>
  );
}
