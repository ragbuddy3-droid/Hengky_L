'use client';

import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { authApi } from '@/lib/api/auth';
import { queryKeys } from '@/lib/query-keys';
import type { User } from '@/types/auth';

export function useMe() {
  const query = useQuery({ queryKey: queryKeys.me, queryFn: authApi.me, retry: false, staleTime: 60_000 });
  // Gagal menghubungi backend diperlakukan sama seperti tamu agar UI tetap bisa dirender.
  const user = query.data ?? null;
  return { ...query, user, isGuest: !query.isPending && !user };
}

/**
 * Ganti identitas (login/daftar/keluar/hapus akun): simpan user baru lalu reset semua data lain,
 * karena dokumen, chat, dan bank soal kini milik pemilik sesi yang berbeda.
 */
function switchIdentity(queryClient: QueryClient, user: User | null) {
  queryClient.setQueryData(queryKeys.me, user);
  return queryClient.resetQueries({ predicate: (q) => q.queryKey[0] !== queryKeys.me[0] });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: authApi.login, onSuccess: (user) => switchIdentity(queryClient, user) });
}

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: authApi.register, onSuccess: (user) => switchIdentity(queryClient, user) });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: authApi.logout, onSuccess: () => switchIdentity(queryClient, null) });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: authApi.updateProfile,
    onSuccess: (user) => queryClient.setQueryData(queryKeys.me, user),
  });
}

export function useChangePassword() {
  return useMutation({ mutationFn: authApi.changePassword });
}

export function useDeleteAccount() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: authApi.deleteAccount, onSuccess: () => switchIdentity(queryClient, null) });
}
