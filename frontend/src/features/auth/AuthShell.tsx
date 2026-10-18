'use client';

import { Box, Group, Text, Title } from '@mantine/core';
import { IconBooks, IconCheck, IconCircleCheck, IconShieldCheck, IconStairsUp } from '@tabler/icons-react';
import { LogoMark } from '@/components/brand/LogoMark';
import { ColorSchemeToggle } from '@/components/layout/ColorSchemeToggle';
import classes from './auth.module.css';

const FEATURES = [
  { icon: IconBooks, label: 'Soal bersumber dari bab buku yang diunggah' },
  { icon: IconStairsUp, label: 'Level Bloom C1–C4 sesuai jenjang SD' },
  { icon: IconShieldCheck, label: 'Divalidasi otomatis sebelum masuk Bank Soal' },
];

const OPTIONS = [
  { key: 'A', text: 'Sebagai sumber energi untuk membuat makanan', correct: true },
  { key: 'B', text: 'Untuk menyerap air dari dalam tanah' },
  { key: 'C', text: 'Agar daun tetap berwarna hijau' },
];

/** Contoh kartu soal sebagai ilustrasi hasil, murni dekoratif. */
function SampleQuestion() {
  return (
    <div className={classes.sample} aria-hidden>
      <div className={classes.card}>
        <Group justify="space-between" mb={10} wrap="nowrap">
          <span className={classes.bloom}>C2 · Memahami</span>
          <Group gap={4} wrap="nowrap" c="green.8">
            <IconCircleCheck size={15} />
            <Text size="xs" fw={600} c="green.8">
              Lolos validasi
            </Text>
          </Group>
        </Group>
        <Text size="sm" fw={600} c="dark.8" lh={1.45} mb={10}>
          Mengapa tumbuhan membutuhkan cahaya matahari dalam proses fotosintesis?
        </Text>
        <div className={classes.options}>
          {OPTIONS.map((o) => (
            <div key={o.key} className={classes.option} data-correct={o.correct || undefined}>
              <span className={classes.optionKey}>{o.correct ? <IconCheck size={12} stroke={3} /> : o.key}</span>
              <span>{o.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function BrandPanel() {
  return (
    <Box component="aside" className={classes.brand} aria-label="Tentang Soalnya">
      <Group gap="sm" wrap="nowrap">
        <LogoMark size={40} />
        <Text fw={700} fz="xl">
          Soalnya
        </Text>
      </Group>

      <div className={classes.hero}>
        <Title order={2} fz={{ md: 30, lg: 36 }} lh={1.2} c="white" maw={460}>
          Ubah buku pelajaran menjadi <span className={classes.highlight}>bank soal</span> yang siap pakai.
        </Title>
        <SampleQuestion />
      </div>

      <ul className={classes.features}>
        {FEATURES.map(({ icon: Icon, label }) => (
          <li key={label}>
            <Icon size={18} stroke={1.75} aria-hidden />
            <Text size="sm" c="indigo.0">
              {label}
            </Text>
          </li>
        ))}
      </ul>
    </Box>
  );
}

export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className={classes.root}>
      <BrandPanel />
      <Box component="main" className={classes.formSide}>
        <div className={classes.themeToggle}>
          <ColorSchemeToggle />
        </div>
        <div className={classes.formInner}>
          <Group gap="xs" mb="xl" hiddenFrom="md">
            <LogoMark size={36} />
            <Text fw={700} fz="lg">
              Soalnya
            </Text>
          </Group>
          {children}
        </div>
      </Box>
    </div>
  );
}
