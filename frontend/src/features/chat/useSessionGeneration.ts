'use client';

import { useEffect, useRef } from 'react';
import { notifications } from '@mantine/notifications';
import { useQueryClient } from '@tanstack/react-query';
import { useChatMessages, useChatSession } from '@/hooks/useChat';
import { queryKeys } from '@/lib/query-keys';
import type { GenerationStatus } from '@/types/chat';
import { useGenerationStream } from './useGenerationStream';

const POLL_MS = 4000;

/**
 * Sesi + pesan + status generasi soal. Selama `generation_status` sesi bernilai 'running', progres datang
 * lewat SSE (dengan polling sesi sebagai cadangan); begitu berubah ke 'done'/'failed', pesan dan daftar
 * soal di-refresh dan pengguna diberi notifikasi.
 */
export function useSessionGeneration(sessionId: string) {
  const queryClient = useQueryClient();
  const sessionQuery = useChatSession(sessionId, (s) => (s?.generation_status === 'running' ? POLL_MS : false));
  const messagesQuery = useChatMessages(sessionId);

  const session = sessionQuery.data;
  const status = session?.generation_status;
  const running = status === 'running';
  const progress = useGenerationStream(sessionId, running);

  const previousStatus = useRef<GenerationStatus | undefined>(undefined);
  useEffect(() => {
    const wasRunning = previousStatus.current === 'running';
    previousStatus.current = status;
    if (!wasRunning || !status || status === 'running') return;

    queryClient.invalidateQueries({ queryKey: queryKeys.messages(sessionId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.questions(sessionId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.questions() });
    queryClient.invalidateQueries({ queryKey: queryKeys.sessions, exact: true });

    const failed = status === 'failed';
    notifications.show({
      color: failed ? 'red' : 'green',
      title: failed ? 'Soal gagal dibuat' : 'Soal selesai dibuat',
      message: failed ? 'Lihat pesan terakhir di percakapan untuk penyebabnya.' : 'Lihat hasilnya di panel "Soal di sesi ini".',
    });
  }, [status, queryClient, sessionId]);

  return {
    sessionQuery,
    messagesQuery,
    pending:
      running && session?.generation_message_id
        ? { messageId: session.generation_message_id, count: session.generation_count ?? 0 }
        : null,
    /** Progres langsung dari server selama generasi berjalan. */
    progress,
    /** Generasi tercatat berjalan, tetapi server tidak bisa dihubungi saat polling. */
    unreachable: running && sessionQuery.isRefetchError,
  };
}
