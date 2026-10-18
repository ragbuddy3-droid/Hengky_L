'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { notifications } from '@mantine/notifications';
import { chatApi } from '@/lib/api/chat';
import { queryKeys } from '@/lib/query-keys';
import type { ChatMessage, ChatSessionListItem } from '@/types/chat';

export function useChatSessions() {
  return useQuery({ queryKey: queryKeys.sessions, queryFn: () => chatApi.listSessions() });
}

type PollInterval = number | false;

/** `pollMs` bisa berupa fungsi dari data sesi terbaru, untuk polling bersyarat. */
export function useChatSession(
  sessionId: string,
  pollMs: PollInterval | ((session: ChatSessionListItem | undefined) => PollInterval) = false,
) {
  return useQuery({
    queryKey: queryKeys.session(sessionId),
    queryFn: () => chatApi.getSession(sessionId),
    refetchInterval: typeof pollMs === 'function' ? (query) => pollMs(query.state.data) : pollMs,
  });
}

export function useChatMessages(sessionId: string) {
  return useQuery({ queryKey: queryKeys.messages(sessionId), queryFn: () => chatApi.messages(sessionId) });
}

const GUEST_TOAST_KEY = 'soalnya:guest-toast-shown';

/** Sekali per browser: ingatkan tamu bahwa riwayatnya sementara. localStorage bisa diblokir, jadi dibungkus try/catch. */
function showGuestToastOnce() {
  try {
    if (localStorage.getItem(GUEST_TOAST_KEY)) return;
    localStorage.setItem(GUEST_TOAST_KEY, '1');
  } catch {
    return;
  }
  notifications.show({
    color: 'accent',
    title: 'Anda sedang dalam mode tamu',
    message: 'Riwayat chat hanya tersimpan di browser ini selama 24 jam. Masuk atau daftar untuk menyimpannya.',
    autoClose: 8000,
  });
}

export function useCreateSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: chatApi.createSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
      const me = queryClient.getQueryState(queryKeys.me);
      if (me?.status === 'success' && me.data === null) showGuestToastOnce();
    },
  });
}

export function useDeleteSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: chatApi.removeSession,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.sessions }),
  });
}

/** Kirim pesan dengan pembaruan optimistis: pesan user langsung tampil sebelum balasan datang. */
export function useSendMessage(sessionId: string) {
  const queryClient = useQueryClient();
  const key = queryKeys.messages(sessionId);

  return useMutation({
    mutationFn: (content: string) => chatApi.sendMessage(sessionId, content),
    onMutate: async (content) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<ChatMessage[]>(key);
      const optimistic: ChatMessage = { id: `temp-${Date.now()}`, role: 'user', content };
      queryClient.setQueryData<ChatMessage[]>(key, (old) => [...(old ?? []), optimistic]);
      return { previous };
    },
    onError: (_err, _content, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: key });
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
    },
  });
}
