'use client';

import { Box, Group, Progress, Stack, Text, VisuallyHidden } from '@mantine/core';
import { IconCheck, IconX } from '@tabler/icons-react';

export const MIN_PASSWORD_LENGTH = 8;

const REQUIREMENTS = [
  { re: /[a-z]/, label: 'Huruf kecil' },
  { re: /[A-Z]/, label: 'Huruf besar' },
  { re: /[0-9]/, label: 'Angka' },
  { re: /[^A-Za-z0-9]/, label: 'Simbol' },
];

const LEVELS = [
  { label: 'Terlalu pendek', color: 'red' },
  { label: 'Lemah', color: 'red' },
  { label: 'Sedang', color: 'accent' },
  { label: 'Kuat', color: 'teal' },
  { label: 'Sangat kuat', color: 'teal' },
];

/** 0 = kurang dari panjang minimum, 1–4 = jumlah variasi karakter yang terpenuhi. */
function strength(password: string) {
  if (password.length < MIN_PASSWORD_LENGTH) return 0;
  return Math.max(1, REQUIREMENTS.filter((r) => r.re.test(password)).length);
}

/** Indikator kekuatan password. Hanya panjang minimum yang diwajibkan; variasi karakter sekadar saran. */
export function PasswordStrength({ value }: { value: string }) {
  if (!value) return null;
  const score = strength(value);
  const level = LEVELS[score];

  return (
    <Stack gap={6} mt={-6}>
      <Group gap={4} grow aria-hidden>
        {Array.from({ length: 4 }, (_, i) => (
          <Progress key={i} size={4} value={i < score ? 100 : 0} color={level.color} transitionDuration={150} />
        ))}
      </Group>
      <Text size="xs" c="dimmed" aria-live="polite">
        Kekuatan password:{' '}
        <Box component="span" fw={600} c="var(--mantine-color-text)">
          {level.label}
        </Box>
      </Text>
      <Group gap="sm" style={{ rowGap: 4 }}>
        <Requirement met={value.length >= MIN_PASSWORD_LENGTH} label={`Min. ${MIN_PASSWORD_LENGTH} karakter`} />
        {REQUIREMENTS.map((r) => (
          <Requirement key={r.label} met={r.re.test(value)} label={r.label} />
        ))}
      </Group>
    </Stack>
  );
}

function Requirement({ met, label }: { met: boolean; label: string }) {
  return (
    <Group gap={4} c={met ? 'var(--app-success-text)' : 'dimmed'} wrap="nowrap">
      {met ? <IconCheck size={14} aria-hidden /> : <IconX size={14} aria-hidden />}
      <Text size="xs">
        {label}
        <VisuallyHidden>{met ? ' (terpenuhi)' : ' (belum terpenuhi)'}</VisuallyHidden>
      </Text>
    </Group>
  );
}
