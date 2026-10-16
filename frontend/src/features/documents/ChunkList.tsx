'use client';

import { useMemo, useState } from 'react';
import {
  Badge,
  Card,
  Group,
  Highlight,
  Paper,
  Select,
  Skeleton,
  Spoiler,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { AppPagination } from '@/components/common/AppPagination';
import { IconSearch } from '@tabler/icons-react';
import { CHUNK_CATEGORY_LABELS, formatNumber } from '@/lib/format';
import type { DocumentChunk } from '@/types/document';

const PAGE_SIZE = 20;

/** Urutkan label bab secara alami ("2" sebelum "10"). */
const naturalSort = (a: string, b: string) => a.localeCompare(b, 'id', { numeric: true });

export function ChunkList({ chunks, isLoading }: { chunks: DocumentChunk[] | undefined; isLoading: boolean }) {
  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 200);
  const [chapter, setChapter] = useState<string | null>(null);
  const [category, setCategory] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const chapterOptions = useMemo(
    () => [...new Set((chunks ?? []).map((c) => c.chapter).filter((c): c is string => !!c))].sort(naturalSort),
    [chunks],
  );
  const categoryOptions = useMemo(
    () =>
      [...new Set((chunks ?? []).map((c) => c.category).filter(Boolean))].map((value) => ({
        value,
        label: CHUNK_CATEGORY_LABELS[value] ?? value,
      })),
    [chunks],
  );

  const filtered = useMemo(() => {
    const q = debouncedSearch.trim().toLowerCase();
    return (chunks ?? []).filter(
      (c) =>
        (!chapter || c.chapter === chapter) &&
        (!category || c.category === category) &&
        (!q || c.text.toLowerCase().includes(q) || c.section_heading?.toLowerCase().includes(q)),
    );
  }, [chunks, chapter, category, debouncedSearch]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const resetPage = () => setPage(1);

  if (isLoading) {
    return (
      <Stack gap="sm">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} h={120} radius="md" />
        ))}
      </Stack>
    );
  }

  return (
    <Stack gap="md">
      <Paper p="sm">
        <Group gap="sm" align="flex-end">
          <TextInput
            label="Cari teks"
            placeholder="Kata kunci di isi atau judul bagian"
            leftSection={<IconSearch size={16} aria-hidden />}
            value={search}
            onChange={(e) => {
              setSearch(e.currentTarget.value);
              resetPage();
            }}
            style={{ flex: '2 1 240px' }}
          />
          <Select
            label="Bab"
            placeholder="Semua bab"
            data={chapterOptions}
            value={chapter}
            onChange={(v) => {
              setChapter(v);
              resetPage();
            }}
            clearable
            searchable
            disabled={!chapterOptions.length}
            style={{ flex: '1 1 160px' }}
          />
          <Select
            label="Kategori"
            placeholder="Semua kategori"
            data={categoryOptions}
            value={category}
            onChange={(v) => {
              setCategory(v);
              resetPage();
            }}
            clearable
            style={{ flex: '1 1 180px' }}
          />
        </Group>
      </Paper>

      <Text size="sm" c="dimmed" aria-live="polite">
        Menampilkan {formatNumber(filtered.length)} dari {formatNumber(chunks?.length ?? 0)} potongan teks
      </Text>

      {visible.length === 0 ? (
        <Text c="dimmed" ta="center" py="xl">
          Tidak ada potongan teks yang cocok.
        </Text>
      ) : (
        visible.map((chunk, i) => (
          <Card key={chunk.id} padding="md">
            <Group justify="space-between" mb="xs" gap="xs">
              <Group gap={6}>
                <Text size="xs" c="dimmed" fw={600}>
                  #{(currentPage - 1) * PAGE_SIZE + i + 1}
                </Text>
                {chunk.chapter && (
                  <Badge color="teal" tt="none" maw={260} title={chunk.chapter}>
                    {chunk.chapter}
                  </Badge>
                )}
                {chunk.category && (
                  <Badge color="gray" variant="outline">
                    {CHUNK_CATEGORY_LABELS[chunk.category] ?? chunk.category}
                  </Badge>
                )}
              </Group>
              <Text size="xs" c="dimmed">
                {formatNumber(chunk.word_count)} kata
              </Text>
            </Group>
            {chunk.section_heading && (
              <Text fw={600} size="sm" mb={4}>
                {chunk.section_heading}
              </Text>
            )}
            <Spoiler maxHeight={96} showLabel="Tampilkan semua" hideLabel="Sembunyikan">
              <Highlight highlight={debouncedSearch.trim()} size="sm" lh={1.6} style={{ whiteSpace: 'pre-wrap' }}>
                {chunk.text}
              </Highlight>
            </Spoiler>
          </Card>
        ))
      )}

      <AppPagination total={totalPages} value={currentPage} onChange={setPage} />
    </Stack>
  );
}
