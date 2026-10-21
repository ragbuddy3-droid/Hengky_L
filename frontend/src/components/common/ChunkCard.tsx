import { Badge, Card, Group, Spoiler, Text } from '@mantine/core';
import { CHUNK_CATEGORY_LABELS } from '@/lib/format';

/** Kartu satu potongan teks buku: nomor, bab, kategori, judul bagian, lalu isi yang bisa dibuka-tutup. */
export function ChunkCard({
  index,
  chunk,
  meta,
  children,
}: {
  index: number;
  chunk: { chapter?: string | null; category: string; section_heading?: string | null };
  /** Info di pojok kanan atas (jumlah kata, nomor halaman). */
  meta?: string | null;
  children: React.ReactNode;
}) {
  return (
    <Card padding="md">
      <Group justify="space-between" mb="xs" gap="xs">
        <Group gap={6}>
          <Text size="xs" c="dimmed" fw={600}>
            #{index}
          </Text>
          {chunk.chapter && (
            <Badge tt="none" maw={260} title={chunk.chapter}>
              {chunk.chapter}
            </Badge>
          )}
          {chunk.category && (
            <Badge color="gray" variant="outline">
              {CHUNK_CATEGORY_LABELS[chunk.category] ?? chunk.category}
            </Badge>
          )}
        </Group>
        {meta && (
          <Text size="xs" c="dimmed">
            {meta}
          </Text>
        )}
      </Group>
      {chunk.section_heading && (
        <Text fw={600} size="sm" mb={4}>
          {chunk.section_heading}
        </Text>
      )}
      <Spoiler maxHeight={96} showLabel="Tampilkan semua" hideLabel="Sembunyikan">
        {children}
      </Spoiler>
    </Card>
  );
}
