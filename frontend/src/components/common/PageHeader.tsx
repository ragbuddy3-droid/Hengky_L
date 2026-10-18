'use client';

import Link from 'next/link';
import { Anchor, Box, Breadcrumbs, Group, Text, Title } from '@mantine/core';

/** Skala judul halaman yang sama di semua halaman (app, auth, chat baru). */
export const PAGE_TITLE_FZ = { base: 24, sm: 28 };

export type Crumb = { label: React.ReactNode; href?: string };

/** Jejak navigasi di atas judul; item terakhir tanpa `href` menjadi halaman aktif. */
export function PageBreadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <Breadcrumbs mb="md" fz="sm" separator={<Text span c="dimmed" aria-hidden>/</Text>}>
      {items.map((c, i) =>
        c.href ? (
          <Anchor key={i} component={Link} href={c.href}>
            {c.label}
          </Anchor>
        ) : (
          <Text key={i} size="sm" c="dimmed" truncate maw={280} aria-current="page">
            {c.label}
          </Text>
        ),
      )}
    </Breadcrumbs>
  );
}

export function PageHeader({
  title,
  description,
  meta,
  actions,
  breadcrumbs,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  /** Baris kecil di bawah judul, misalnya badge status. */
  meta?: React.ReactNode;
  actions?: React.ReactNode;
  breadcrumbs?: Crumb[];
}) {
  return (
    <>
      {breadcrumbs && <PageBreadcrumbs items={breadcrumbs} />}
      <Group justify="space-between" align="flex-start" gap="md" mb="lg">
        <Box miw={0} style={{ flex: '1 1 320px' }}>
          <Title order={1} fz={PAGE_TITLE_FZ} style={{ overflowWrap: 'anywhere' }}>
            {title}
          </Title>
          {description && (
            <Text c="dimmed" size="sm" mt={4} maw={640}>
              {description}
            </Text>
          )}
          {meta && (
            <Group gap="xs" mt={6}>
              {meta}
            </Group>
          )}
        </Box>
        {actions && <Group gap="sm">{actions}</Group>}
      </Group>
    </>
  );
}
