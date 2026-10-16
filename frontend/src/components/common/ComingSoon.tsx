'use client';

import { IconTools } from '@tabler/icons-react';
import { EmptyState } from './EmptyState';
import { PageContainer } from './PageContainer';
import { PageHeader } from './PageHeader';

/** Placeholder sementara sampai fase implementasi halaman terkait selesai. */
export function ComingSoon({ title, description, phase }: { title: string; description: string; phase: number }) {
  return (
    <PageContainer>
      <PageHeader title={title} description={description} />
      <EmptyState
        icon={<IconTools size={24} aria-hidden />}
        title="Sedang dibangun"
        description={`Halaman ini dikerjakan pada Fase ${phase}.`}
      />
    </PageContainer>
  );
}
