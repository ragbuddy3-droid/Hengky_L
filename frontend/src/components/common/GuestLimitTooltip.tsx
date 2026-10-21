'use client';

import { Box, Tooltip } from '@mantine/core';

/** Sama dengan GUEST_LIMIT_MESSAGES di backend (`services/auth/guest_quota.py`). */
export const GUEST_LIMIT_MESSAGES = {
  upload: 'Mode tamu hanya bisa mengunggah 1 buku. Masuk atau daftar untuk mengunggah lagi.',
  session: 'Mode tamu hanya bisa membuat 1 percakapan. Masuk atau daftar untuk membuat percakapan baru.',
  generate: 'Mode tamu hanya bisa membuat soal 1 kali. Masuk atau daftar untuk membuat soal lagi.',
} as const;

/**
 * Tooltip penjelasan untuk tombol yang dikunci kuota tamu. Tombol `disabled` tidak memicu event mouse,
 * jadi dibungkus span agar tooltip tetap muncul.
 */
export function GuestLimitTooltip({
  kind,
  locked,
  children,
}: {
  kind: keyof typeof GUEST_LIMIT_MESSAGES;
  locked: boolean;
  children: React.ReactNode;
}) {
  if (!locked) return children;
  return (
    <Tooltip label={GUEST_LIMIT_MESSAGES[kind]} multiline w={260} withArrow>
      <Box component="span" display="inline-block">
        {children}
      </Box>
    </Tooltip>
  );
}
