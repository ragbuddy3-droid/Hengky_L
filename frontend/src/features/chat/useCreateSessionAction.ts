'use client';

import { useRouter } from 'next/navigation';
import { notifications } from '@mantine/notifications';
import { useCreateSession } from '@/hooks/useChat';

/** Buat sesi chat untuk dokumen lalu buka halamannya, dengan notifikasi bila gagal. */
export function useCreateSessionAction() {
  const router = useRouter();
  const createSession = useCreateSession();

  const start = (documentId: string) =>
    createSession.mutate(documentId, {
      onSuccess: (session) => router.push(`/chat/${session.id}`),
      onError: (err) => notifications.show({ color: 'red', title: 'Gagal membuat sesi', message: err.message }),
    });

  return { start, isPending: createSession.isPending };
}
