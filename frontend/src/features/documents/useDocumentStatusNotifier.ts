'use client';

import { useEffect, useRef } from 'react';
import { notifications } from '@mantine/notifications';
import { isProcessing } from '@/hooks/useDocuments';
import type { DocumentItem } from '@/types/document';

/** Tampilkan notifikasi saat status dokumen berpindah dari diproses ke siap/gagal. */
export function useDocumentStatusNotifier(docs: DocumentItem[] | undefined) {
  const previous = useRef<Map<string, string> | null>(null);

  useEffect(() => {
    if (!docs) return;
    const prev = previous.current;
    if (prev) {
      for (const doc of docs) {
        const before = prev.get(doc.id);
        if (before === doc.status || !isProcessing(before)) continue;
        if (doc.status === 'ready' && doc.warning_message) {
          notifications.show({ color: 'yellow', title: 'Buku siap, dengan catatan', message: doc.warning_message });
        } else if (doc.status === 'ready') {
          notifications.show({ color: 'green', title: 'Buku siap', message: `${doc.filename} siap dipakai untuk membuat soal.` });
        } else if (doc.status === 'failed') {
          notifications.show({ color: 'red', title: 'Pemrosesan gagal', message: doc.error_message || doc.filename });
        }
      }
    }
    previous.current = new Map(docs.map((d) => [d.id, d.status]));
  }, [docs]);
}
