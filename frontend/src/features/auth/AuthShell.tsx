'use client';

import { Badge, Box, Group, Stack, Text, Title } from '@mantine/core';
import { IconBooks, IconCircleCheck, IconShieldCheck, IconStairsUp } from '@tabler/icons-react';
import { LogoMark } from '@/components/brand/LogoMark';
import { ColorSchemeToggle } from '@/components/layout/ColorSchemeToggle';
import classes from './auth.module.css';

const FEATURES = [
  { icon: IconBooks, title: 'Dari isi bukumu sendiri', text: 'Setiap soal bersumber dari bab yang kamu unggah.' },
  { icon: IconStairsUp, title: 'Level Bloom C1–C6', text: 'Atur tingkat berpikir sesuai tujuan pembelajaran.' },
  { icon: IconShieldCheck, title: 'Divalidasi berlapis', text: 'Soal dicek otomatis sebelum masuk Bank Soal.' },
];

function BrandPanel() {
  return (
    <Box component="aside" className={classes.brand} aria-label="Tentang Soalnya">
      <Group gap="sm" wrap="nowrap">
        <LogoMark size={40} />
        <Text fw={700} fz="xl">
          Soalnya
        </Text>
      </Group>

      <Stack gap="xl" maw={460}>
        <Title order={2} fz={{ md: 30, lg: 36 }} lh={1.2} c="white">
          Ubah buku pelajaran menjadi bank soal yang siap pakai.
        </Title>
        <Stack gap="md" component="ul" m={0} p={0} style={{ listStyle: 'none' }}>
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <Group key={title} component="li" gap="sm" wrap="nowrap" align="flex-start">
              <span className={classes.featureIcon}>
                <Icon size={20} stroke={1.75} aria-hidden />
              </span>
              <Box>
                <Text fw={600} c="white">
                  {title}
                </Text>
                <Text size="sm" c="indigo.1">
                  {text}
                </Text>
              </Box>
            </Group>
          ))}
        </Stack>
      </Stack>

      {/* Contoh kartu soal sebagai ilustrasi hasil, murni dekoratif. */}
      <Box className={classes.sample} aria-hidden>
        <Group justify="space-between" mb={8}>
          <Badge color="accent.4" c="dark.9" variant="filled">
            C2 · Memahami
          </Badge>
          <Group gap={4} c="green.2">
            <IconCircleCheck size={16} />
            <Text size="xs" fw={600}>
              Lolos validasi
            </Text>
          </Group>
        </Group>
        <Text size="sm" c="white" fw={500}>
          Mengapa tumbuhan membutuhkan cahaya matahari dalam proses fotosintesis?
        </Text>
      </Box>
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
