'use client';

import { notifications } from '@mantine/notifications';
import { confirmDelete } from '@/components/common/confirmDelete';
import { useDeleteSession } from '@/hooks/useChat';

/** Konfirmasi + hapus sesi chat, dengan notifikasi hasil. */
export function useDeleteSessionAction(onDeleted?: (id: string) => void) {
  const deleteSession = useDeleteSession();

  return (id: string) =>
    confirmDelete({
      title: 'Hapus sesi chat?',
      message: 'Riwayat percakapan sesi ini akan dihapus.',
      onConfirm: () =>
        deleteSession.mutate(id, {
          onSuccess: () => {
            notifications.show({ color: 'green', message: 'Sesi chat dihapus.' });
            onDeleted?.(id);
          },
          onError: (err) => notifications.show({ color: 'red', title: 'Gagal menghapus', message: err.message }),
        }),
    });
}
