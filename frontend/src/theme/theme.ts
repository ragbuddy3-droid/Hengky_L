import { createTheme, type MantineColorsTuple } from '@mantine/core';

// Palet diambil dari skala Tailwind agar shade 7 (primaryShade) lolos kontras WCAG AA (≥ 4.5:1)
// untuk teks putih di atas tombol/badge berwarna.

// Teal utama — shade 7 = #0f766e (5.47:1 dengan putih).
const teal: MantineColorsTuple = [
  '#f0fdfa',
  '#ccfbf1',
  '#99f6e4',
  '#5eead4',
  '#2dd4bf',
  '#14b8a6',
  '#0d9488',
  '#0f766e',
  '#115e59',
  '#134e4a',
];

// Aksen oranye — khusus aksi utama "Buat Soal". Shade 7 = #c2410c (5.18:1 dengan putih).
const accent: MantineColorsTuple = [
  '#fff7ed',
  '#ffedd5',
  '#fed7aa',
  '#fdba74',
  '#fb923c',
  '#f97316',
  '#ea580c',
  '#c2410c',
  '#9a3412',
  '#7c2d12',
];

export const theme = createTheme({
  primaryColor: 'teal',
  primaryShade: { light: 7, dark: 7 },
  colors: { teal, accent },
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
  },
});

/**
 * Warna badge per level Bloom (C1–C6). Shade dipilih eksplisit supaya teks putih
 * di atasnya tetap ≥ 4.5:1 (gray.7 8.2 · blue.8 5.0 · cyan.9 5.6 · teal.7 5.5 · violet.7 5.6 · grape.8 5.8).
 */
export const BLOOM_COLORS: Record<string, string> = {
  C1: 'gray.7',
  C2: 'blue.8',
  C3: 'cyan.9',
  C4: 'teal.7',
  C5: 'violet.7',
  C6: 'grape.8',
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
  { value: 'C5', label: 'C5 · Mengevaluasi' },
  { value: 'C6', label: 'C6 · Mencipta' },
];
