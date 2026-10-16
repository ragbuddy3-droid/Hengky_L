'use client';

import { useMemo, useState } from 'react';
import { Button, Group, NumberInput, Popover, Select, Stack, Text, TextInput } from '@mantine/core';
import { IconAdjustments, IconSparkles } from '@tabler/icons-react';
import { useDocumentChunks } from '@/hooks/useDocuments';
import { BLOOM_LEVELS } from '@/theme/theme';
import { buildGenerationPrompt, chapterNumber } from './prompts';

/** Popover untuk menyusun permintaan soal secara terstruktur (jumlah, level Bloom, bab). */
export function ParamsPopover({
  documentId,
  disabled,
  onSubmit,
}: {
  documentId?: string;
  disabled?: boolean;
  onSubmit: (prompt: string) => void;
}) {
  const [opened, setOpened] = useState(false);
  const [count, setCount] = useState<number | string>(5);
  const [bloom, setBloom] = useState<string | null>(null);
  const [chapter, setChapter] = useState<string | null>(null);

  // Daftar bab diambil dari potongan teks buku (hanya saat popover dibuka).
  const { data: chunks, isLoading } = useDocumentChunks(documentId ?? '', opened && !!documentId);
  const chapterOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const c of chunks ?? []) {
      const num = c.chapter ? chapterNumber(c.chapter) : null;
      if (num && !seen.has(num)) seen.set(num, c.chapter!);
    }
    return [...seen].map(([value, label]) => ({ value, label }));
  }, [chunks]);

  const validCount = typeof count === 'number' && count >= 1 && count <= 20;
  const prompt = validCount ? buildGenerationPrompt({ count, bloom, chapter }) : '';

  return (
    <Popover opened={opened} onChange={setOpened} position="top-start" width={320} trapFocus shadow="md">
      <Popover.Target>
        <Button
          variant="default"
          size="xs"
          leftSection={<IconAdjustments size={14} aria-hidden />}
          onClick={() => setOpened((o) => !o)}
          disabled={disabled}
        >
          Atur parameter
        </Button>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="sm">
          <NumberInput label="Jumlah soal" min={1} max={20} clampBehavior="strict" value={count} onChange={setCount} />
          <Select label="Level Bloom" placeholder="Beragam level" data={BLOOM_LEVELS} value={bloom} onChange={setBloom} clearable />
          {chapterOptions.length || isLoading ? (
            <Select
              label="Bab"
              placeholder={isLoading ? 'Memuat daftar bab…' : 'Semua bab'}
              data={chapterOptions}
              value={chapter}
              onChange={setChapter}
              clearable
              searchable
              disabled={isLoading}
            />
          ) : (
            <TextInput
              label="Bab"
              placeholder="Semua bab (mis. 2)"
              value={chapter ?? ''}
              onChange={(e) => setChapter(e.currentTarget.value.trim() || null)}
            />
          )}
          <Text size="xs" c="dimmed">
            Pesan yang dikirim: <Text span fw={600} c="var(--mantine-color-text)">{prompt || '—'}</Text>
          </Text>
          <Group justify="flex-end">
            <Button
              color="accent"
              size="sm"
              leftSection={<IconSparkles size={16} aria-hidden />}
              disabled={!validCount}
              onClick={() => {
                onSubmit(prompt);
                setOpened(false);
              }}
            >
              Buat Soal
            </Button>
          </Group>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
