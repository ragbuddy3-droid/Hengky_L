'use client';

import { Text } from '@mantine/core';
import { modals } from '@mantine/modals';
import { DANGER_COLOR } from '@/theme/theme';

export function confirmDelete({
  title,
  message,
  onConfirm,
}: {
  title: string;
  message: React.ReactNode;
  onConfirm: () => void;
}) {
  modals.openConfirmModal({
    title,
    children: <Text size="sm">{message}</Text>,
    labels: { confirm: 'Hapus', cancel: 'Batal' },
    confirmProps: { color: DANGER_COLOR },
    onConfirm,
  });
}
