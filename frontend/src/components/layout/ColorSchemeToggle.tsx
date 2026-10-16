'use client';

import { ActionIcon, Box, Tooltip, useComputedColorScheme, useMantineColorScheme } from '@mantine/core';
import { IconMoon, IconSun } from '@tabler/icons-react';

export function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const computed = useComputedColorScheme('light', { getInitialValueInEffect: true });

  return (
    <Tooltip label="Ganti tema terang/gelap">
      <ActionIcon
        variant="default"
        size="lg"
        onClick={() => setColorScheme(computed === 'dark' ? 'light' : 'dark')}
        aria-label="Ganti tema terang/gelap"
      >
        {/* Kedua ikon dirender dan disembunyikan via CSS agar tidak ada hydration mismatch. */}
        <Box component="span" lh={0} lightHidden>
          <IconSun size={18} aria-hidden />
        </Box>
        <Box component="span" lh={0} darkHidden>
          <IconMoon size={18} aria-hidden />
        </Box>
      </ActionIcon>
    </Tooltip>
  );
}
