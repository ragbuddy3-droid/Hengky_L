'use client';

import { Group, Pagination } from '@mantine/core';

/** Pagination berlabel bahasa Indonesia yang menggulir ke atas saat pindah halaman. */
export function AppPagination({ total, value, onChange }: { total: number; value: number; onChange: (page: number) => void }) {
  if (total <= 1) return null;

  return (
    <Group justify="center" mt="lg">
      <Pagination
        total={total}
        value={value}
        onChange={(p) => {
          onChange(p);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }}
        getControlProps={(control) => ({
          'aria-label':
            control === 'next'
              ? 'Halaman berikutnya'
              : control === 'previous'
                ? 'Halaman sebelumnya'
                : control === 'first'
                  ? 'Halaman pertama'
                  : 'Halaman terakhir',
        })}
        getItemProps={(page) => ({ 'aria-label': `Halaman ${page}` })}
      />
    </Group>
  );
}
