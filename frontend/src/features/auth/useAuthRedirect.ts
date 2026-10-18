'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useMe } from '@/hooks/useAuth';

/** Hanya izinkan path internal (bukan `//host` atau URL absolut) agar `?next=` tidak bisa jadi open redirect. */
export function safeNext(next?: string | null) {
  return next && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/\\') ? next : '/chat';
}

/** Arahkan pengguna yang sudah login keluar dari halaman masuk/daftar. */
export function useRedirectIfLoggedIn(next: string) {
  const router = useRouter();
  const { user } = useMe();
  useEffect(() => {
    if (user) router.replace(next);
  }, [user, next, router]);
  return Boolean(user);
}
