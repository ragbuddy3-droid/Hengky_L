'use client';

import { notifications } from '@mantine/notifications';
import { confirmDelete } from '@/components/common/confirmDelete';
import { useDeleteDocument } from '@/hooks/useDocuments';
import type { DocumentItem } from '@/types/document';

/** Konfirmasi + hapus dokumen, dengan notifikasi hasil. */
export function useDeleteDocumentAction(onDeleted?: () => void) {
  const deleteDocument = useDeleteDocument();

  return (doc: Pick<DocumentItem, 'id' | 'filename'>) =>
    confirmDelete({
      title: 'Hapus buku?',
      message: `"${doc.filename}" beserta seluruh potongan teksnya akan dihapus permanen. Soal yang sudah dibuat dari buku ini tidak bisa dibuat ulang.`,
      onConfirm: () =>
        deleteDocument.mutate(doc.id, {
          onSuccess: () => {
            notifications.show({ color: 'teal', message: `"${doc.filename}" dihapus.` });
            onDeleted?.();
          },
          onError: (err) => notifications.show({ color: 'red', title: 'Gagal menghapus', message: err.message }),
        }),
    });
}
