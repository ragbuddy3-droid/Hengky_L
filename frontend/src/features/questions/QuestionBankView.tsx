'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  Button,
  Group,
  MultiSelect,
  Paper,
  SegmentedControl,
  Select,
  Skeleton,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconListCheck, IconSearch, IconSparkles } from '@tabler/icons-react';
import { AppPagination } from '@/components/common/AppPagination';
import { EmptyState } from '@/components/common/EmptyState';
import { PageContainer } from '@/components/common/PageContainer';
import { PageHeader } from '@/components/common/PageHeader';
import { QueryError } from '@/components/common/QueryError';
import { useQuestions } from '@/hooks/useQuestions';
import { bloomCode, formatNumber, QUESTION_STATUS_LABELS, QUESTION_TYPE_LABELS } from '@/lib/format';
import { BLOOM_LEVELS } from '@/theme/theme';
import { ExportMenu } from './ExportMenu';
import { QuestionCard } from './QuestionCard';
import { QuestionStats } from './QuestionStats';

const PAGE_SIZE = 20;
type StatusFilter = 'all' | 'final' | 'needs_review';

export function QuestionBankView() {
  const { data, isLoading, error, refetch } = useQuestions();
  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 200);
  const [blooms, setBlooms] = useState<string[]>([]);
  const [status, setStatus] = useState<StatusFilter>('all');
  const [type, setType] = useState<string | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const questions = useMemo(() => data ?? [], [data]);
  const typeOptions = useMemo(
    () =>
      [...new Set(questions.map((q) => q.question_type))].map((value) => ({
        value,
        label: QUESTION_TYPE_LABELS[value] ?? value,
      })),
    [questions],
  );
  const documentOptions = useMemo(() => {
    const names = new Map<string, string>();
    for (const q of questions) {
      if (q.document_id && !names.has(q.document_id)) names.set(q.document_id, q.document_filename ?? 'Dokumen tanpa nama');
    }
    return [...names].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label));
  }, [questions]);

  const filtered = useMemo(() => {
    const q = debouncedSearch.trim().toLowerCase();
    return questions.filter(
      (item) =>
        (status === 'all' || item.status === status) &&
        (!type || item.question_type === type) &&
        (!documentId || item.document_id === documentId) &&
        (!blooms.length || blooms.includes(bloomCode(item.bloom_level) ?? '')) &&
        (!q ||
          item.question_text.toLowerCase().includes(q) ||
          item.answer_key.toLowerCase().includes(q) ||
          item.source_reference?.toLowerCase().includes(q)),
    );
  }, [questions, status, type, documentId, blooms, debouncedSearch]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const hasFilters = !!(search || blooms.length || status !== 'all' || type || documentId);

  const resetFilters = () => {
    setSearch('');
    setBlooms([]);
    setStatus('all');
    setType(null);
    setDocumentId(null);
    setPage(1);
  };

  let content: React.ReactNode;
  if (isLoading) {
    content = (
      <Stack gap="sm">
        <Skeleton h={96} radius="md" />
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} h={96} radius="md" />
        ))}
      </Stack>
    );
  } else if (error) {
    content = <QueryError error={error} onRetry={() => refetch()} />;
  } else if (!questions.length) {
    content = (
      <EmptyState
        icon={<IconListCheck size={24} aria-hidden />}
        title="Belum ada soal"
        description="Soal yang Anda buat lewat chat akan terkumpul di sini untuk ditinjau dan diaudit."
        action={
          <Button component={Link} href="/chat" color="accent" leftSection={<IconSparkles size={16} aria-hidden />}>
            Buat Soal
          </Button>
        }
      />
    );
  } else {
    content = (
      <>
        <QuestionStats questions={questions} />

        <Paper p="sm" mb="md">
          <Stack gap="sm">
            <Group gap="sm" align="flex-end">
              <TextInput
                label="Cari"
                placeholder="Teks soal, kunci jawaban, atau referensi"
                leftSection={<IconSearch size={16} aria-hidden />}
                value={search}
                onChange={(e) => {
                  setSearch(e.currentTarget.value);
                  setPage(1);
                }}
                style={{ flex: '2 1 260px' }}
              />
              <Select
                label="Buku"
                placeholder="Semua buku"
                data={documentOptions}
                value={documentId}
                onChange={(v) => {
                  setDocumentId(v);
                  setPage(1);
                }}
                searchable
                clearable
                style={{ flex: '1 1 200px' }}
              />
              <MultiSelect
                label="Level Bloom"
                placeholder={blooms.length ? undefined : 'Semua level'}
                data={BLOOM_LEVELS}
                value={blooms}
                onChange={(v) => {
                  setBlooms(v);
                  setPage(1);
                }}
                clearable
                style={{ flex: '1 1 200px' }}
              />
              <Select
                label="Tipe soal"
                placeholder="Semua tipe"
                data={typeOptions}
                value={type}
                onChange={(v) => {
                  setType(v);
                  setPage(1);
                }}
                clearable
                style={{ flex: '1 1 160px' }}
              />
            </Group>
            <Group justify="space-between" gap="sm">
              <SegmentedControl
                value={status}
                onChange={(v) => {
                  setStatus(v as StatusFilter);
                  setPage(1);
                }}
                data={[
                  { value: 'all', label: 'Semua' },
                  { value: 'final', label: QUESTION_STATUS_LABELS.final },
                  { value: 'needs_review', label: QUESTION_STATUS_LABELS.needs_review },
                ]}
              />
              {hasFilters && (
                <Button variant="subtle" size="xs" onClick={resetFilters}>
                  Reset filter
                </Button>
              )}
            </Group>
          </Stack>
        </Paper>

        <Text size="sm" c="dimmed" mb="sm" aria-live="polite">
          Menampilkan {formatNumber(filtered.length)} dari {formatNumber(questions.length)} soal
        </Text>

        {visible.length ? (
          <Stack gap="sm">
            {visible.map((q) => (
              <QuestionCard key={q.id} question={q} />
            ))}
          </Stack>
        ) : (
          <Text c="dimmed" ta="center" py="xl">
            Tidak ada soal yang cocok dengan filter.
          </Text>
        )}

        <AppPagination total={totalPages} value={currentPage} onChange={setPage} />
      </>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="Bank Soal"
        description="Semua soal yang telah dibuat. Buka sebuah soal untuk melihat jawaban, sumber, hasil validasi, dan jejak prompt."
        actions={questions.length ? <ExportMenu questions={filtered} title={hasFilters ? 'Bank Soal (terfilter)' : 'Bank Soal'} /> : undefined}
      />
      {content}
    </PageContainer>
  );
}
