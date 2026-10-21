'use client';

import { useMemo, useState } from 'react';
import { Button, Group, Paper, SegmentedControl, SimpleGrid, Skeleton, Text, TextInput } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconBooks, IconSearch, IconUpload } from '@tabler/icons-react';
import { EmptyState } from '@/components/common/EmptyState';
import { GuestLimitTooltip } from '@/components/common/GuestLimitTooltip';
import { PageContainer } from '@/components/common/PageContainer';
import { PageHeader } from '@/components/common/PageHeader';
import { QueryError } from '@/components/common/QueryError';
import { useGuestQuota } from '@/hooks/useAuth';
import { useDocuments } from '@/hooks/useDocuments';
import { DocumentCard } from './DocumentCard';
import { UploadDocumentModal } from './UploadDocumentModal';
import { useDeleteDocumentAction } from './useDeleteDocumentAction';
import { useDocumentStatusNotifier } from './useDocumentStatusNotifier';

type StatusFilter = 'all' | 'ready' | 'processing' | 'failed';

export function DocumentsView() {
  const [uploadOpened, upload] = useDisclosure(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const { data: docs, isLoading, error, refetch } = useDocuments();
  const { canUpload } = useGuestQuota();
  const handleDelete = useDeleteDocumentAction();
  useDocumentStatusNotifier(docs);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (docs ?? []).filter((d) => {
      const matchesText = !q || d.filename.toLowerCase().includes(q) || d.subject.toLowerCase().includes(q);
      const matchesStatus =
        statusFilter === 'all' ||
        (statusFilter === 'processing' ? d.status === 'pending' || d.status === 'processing' : d.status === statusFilter);
      return matchesText && matchesStatus;
    });
  }, [docs, search, statusFilter]);

  const uploadButton = (
    <GuestLimitTooltip kind="upload" locked={!canUpload}>
      <Button leftSection={<IconUpload size={16} aria-hidden />} onClick={upload.open} disabled={!canUpload}>
        Unggah Buku
      </Button>
    </GuestLimitTooltip>
  );

  let content: React.ReactNode;
  if (isLoading) {
    content = (
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} h={148} radius="md" />
        ))}
      </SimpleGrid>
    );
  } else if (error) {
    content = <QueryError error={error} onRetry={() => refetch()} />;
  } else if (!docs?.length) {
    content = (
      <EmptyState
        icon={<IconBooks size={24} aria-hidden />}
        title="Belum ada buku"
        description="Unggah buku pelajaran dalam format PDF. Setelah diproses, Anda bisa langsung meminta soal darinya."
        action={uploadButton}
      />
    );
  } else {
    content = (
      <>
        <Paper p="sm" mb="md">
          <Group justify="space-between" gap="sm">
            <TextInput
              placeholder="Cari judul atau mata pelajaran"
              leftSection={<IconSearch size={16} aria-hidden />}
              value={search}
              onChange={(e) => setSearch(e.currentTarget.value)}
              aria-label="Cari dokumen"
              style={{ flex: '1 1 240px' }}
            />
            <SegmentedControl
              value={statusFilter}
              onChange={(v) => setStatusFilter(v as StatusFilter)}
              data={[
                { value: 'all', label: 'Semua' },
                { value: 'ready', label: 'Siap' },
                { value: 'processing', label: 'Diproses' },
                { value: 'failed', label: 'Gagal' },
              ]}
            />
          </Group>
        </Paper>
        {filtered.length ? (
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
            {filtered.map((doc) => (
              <DocumentCard key={doc.id} doc={doc} onDelete={handleDelete} />
            ))}
          </SimpleGrid>
        ) : (
          <Text c="dimmed" ta="center" py="xl">
            Tidak ada buku yang cocok dengan filter.
          </Text>
        )}
      </>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="Dokumen"
        description={
          docs?.length
            ? `${docs.length} buku tersimpan. Buku berstatus "Siap" bisa langsung dipakai untuk membuat soal.`
            : 'Unggah buku sebagai sumber pembuatan soal.'
        }
        actions={docs?.length ? uploadButton : undefined}
      />
      {content}
      <UploadDocumentModal opened={uploadOpened} onClose={upload.close} />
    </PageContainer>
  );
}
