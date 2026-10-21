import { createTheme, type MantineColorScheme, type MantineColorsTuple } from '@mantine/core';
import { IconDeviceDesktop, IconMoon, IconSun } from '@tabler/icons-react';

// Palet diambil dari skala Tailwind agar shade 7 (primaryShade) lolos kontras WCAG AA (≥ 4.5:1)
// untuk teks putih di atas tombol/badge berwarna.

// Indigo utama — shade 7 = #4338ca (7.9:1 dengan putih).
const indigo: MantineColorsTuple = [
  '#eef2ff',
  '#e0e7ff',
  '#c7d2fe',
  '#a5b4fc',
  '#818cf8',
  '#6366f1',
  '#4f46e5',
  '#4338ca',
  '#3730a3',
  '#312e81',
];

// Aksen amber — khusus aksi utama "Buat Soal" dan percikan logo. Shade 7 = #b45309 (5.0:1 dengan putih).
const accent: MantineColorsTuple = [
  '#fffbeb',
  '#fef3c7',
  '#fde68a',
  '#fcd34d',
  '#fbbf24',
  '#f59e0b',
  '#d97706',
  '#b45309',
  '#92400e',
  '#78350f',
];

export const theme = createTheme({
  primaryColor: 'indigo',
  primaryShade: { light: 7, dark: 7 },
  colors: { indigo, accent },
  fontFamily: 'var(--font-inter), system-ui, sans-serif',
  fontFamilyMonospace: 'var(--font-mono), ui-monospace, monospace',
  headings: { fontFamily: 'var(--font-inter), system-ui, sans-serif', fontWeight: '650' },
  defaultRadius: 'md',
  cursorType: 'pointer',
  focusRing: 'auto',
  components: {
    Card: { defaultProps: { withBorder: true, shadow: 'none', radius: 'md' } },
    Paper: { defaultProps: { withBorder: true, shadow: 'none' } },
    Badge: { defaultProps: { radius: 'sm', variant: 'light' } },
    ActionIcon: { defaultProps: { variant: 'subtle', color: 'gray' } },
    Tooltip: { defaultProps: { withArrow: true, openDelay: 300 } },
    Modal: { defaultProps: { centered: true, radius: 'md' } },
    NavLink: { styles: { root: { borderRadius: 'var(--mantine-radius-md)' } } },
    PasswordInput: {
      defaultProps: {
        visibilityToggleFocusable: true,
        visibilityToggleButtonProps: { 'aria-label': 'Tampilkan atau sembunyikan password' },
      },
    },
  },
});

/** Pilihan skema warna di menu akun dan pengaturan tampilan. */
export const THEME_OPTIONS: { value: MantineColorScheme; label: string; icon: typeof IconSun }[] = [
  { value: 'light', label: 'Terang', icon: IconSun },
  { value: 'dark', label: 'Gelap', icon: IconMoon },
  { value: 'auto', label: 'Sistem', icon: IconDeviceDesktop },
];

/**
 * Warna badge per level Bloom. Soalnya untuk SD, jadi hanya C1–C4 (sama dengan backend).
 * Shade dipilih eksplisit supaya teks putih di atasnya tetap ≥ 4.5:1 (gray.7 8.2 · blue.8 5.0 · cyan.9 5.6 · teal.7 5.5).
 */
export const BLOOM_COLORS: Record<string, string> = {
  C1: 'gray.7',
  C2: 'blue.8',
  C3: 'cyan.9',
  C4: 'teal.7',
};

/** Ubah "cyan.9" menjadi CSS variable Mantine (`var(--mantine-color-cyan-9)`). */
export const colorVar = (color: string) => `var(--mantine-color-${color.replace('.', '-')})`;

/** Warna merah untuk aksi destruktif (red.8 = 4.5:1 dengan putih). */
export const DANGER_COLOR = 'red.8';

export const BLOOM_LEVELS = [
  { value: 'C1', label: 'C1 · Mengingat' },
  { value: 'C2', label: 'C2 · Memahami' },
  { value: 'C3', label: 'C3 · Mengaplikasikan' },
  { value: 'C4', label: 'C4 · Menganalisis' },
];
