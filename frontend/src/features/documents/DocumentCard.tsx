'use client';

import Link from 'next/link';
import { ActionIcon, Anchor, Card, Group, Menu, Stack, Text, ThemeIcon } from '@mantine/core';
import { IconAlertCircle, IconAlertTriangle, IconBook2, IconDots, IconListDetails, IconTrash } from '@tabler/icons-react';
import { DocumentStatusBadge } from '@/components/common/Badges';
import { formatDate } from '@/lib/format';
import type { DocumentItem } from '@/types/document';
import { GenerateQuestionsButton } from './GenerateQuestionsButton';

export function DocumentCard({ doc, onDelete }: { doc: DocumentItem; onDelete: (doc: DocumentItem) => void }) {
  const href = `/documents/${doc.id}`;

  return (
    <Card padding="md" h="100%">
      <Stack gap="sm" h="100%">
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Group gap="sm" wrap="nowrap" miw={0}>
            <ThemeIcon variant="light" size="lg">
              <IconBook2 size={20} aria-hidden />
            </ThemeIcon>
            <Stack gap={0} miw={0}>
              <Anchor component={Link} href={href} fw={600} c="inherit" truncate title={doc.filename}>
                {doc.filename}
              </Anchor>
              <Text size="sm" c="dimmed" truncate>
                {doc.subject}
              </Text>
            </Stack>
          </Group>
          <Menu position="bottom-end">
            <Menu.Target>
              <ActionIcon aria-label={`Opsi untuk ${doc.filename}`}>
                <IconDots size={18} aria-hidden />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item component={Link} href={href} leftSection={<IconListDetails size={14} aria-hidden />}>
                Lihat detail &amp; potongan teks
              </Menu.Item>
              <Menu.Divider />
              <Menu.Item color="red" leftSection={<IconTrash size={14} aria-hidden />} onClick={() => onDelete(doc)}>
                Hapus
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>

        {doc.status === 'failed' && doc.error_message && (
          <Group gap={6} wrap="nowrap" align="flex-start">
            <IconAlertCircle size={16} color="var(--app-danger-text)" style={{ flexShrink: 0, marginTop: 2 }} aria-hidden />
            <Text size="xs" c="var(--app-danger-text)" lineClamp={2} title={doc.error_message}>
              {doc.error_message}
            </Text>
          </Group>
        )}

        {doc.status === 'ready' && doc.warning_message && (
          <Group gap={6} wrap="nowrap" align="flex-start">
            <IconAlertTriangle size={16} color="var(--app-warning-text)" style={{ flexShrink: 0, marginTop: 2 }} aria-hidden />
            <Text size="xs" c="var(--app-warning-text)" lineClamp={2} title={doc.warning_message}>
              {doc.warning_message}
            </Text>
          </Group>
        )}

        <Group justify="space-between" mt="auto" pt="xs">
          <Stack gap={4}>
            <DocumentStatusBadge status={doc.status} />
            <Text size="xs" c="dimmed">
              {formatDate(doc.created_at)}
            </Text>
          </Stack>
          <GenerateQuestionsButton documentId={doc.id} ready={doc.status === 'ready'} size="xs" />
        </Group>
      </Stack>
    </Card>
  );
}
