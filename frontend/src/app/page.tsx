'use client';

import { Title, Text, SimpleGrid, Card, Group, ThemeIcon, Button, Stack, Badge, Paper, Box } from '@mantine/core';
import { IconBook, IconMessage2, IconQuestionMark, IconArrowRight, IconShieldCheck, IconCpu, IconSparkles } from '@tabler/icons-react';
import Link from 'next/link';

export default function HomePage() {
  return (
    <Stack gap="lg">
      <Paper
        p="xl"
        radius="lg"
        style={{
          background: 'linear-gradient(135deg, rgba(34, 139, 230, 0.1) 0%, rgba(21, 170, 191, 0.1) 100%)',
          border: '1px solid rgba(34, 139, 230, 0.2)',
        }}
      >
        <Group justify="space-between" align="flex-start">
          <Box style={{ maxWidth: '650px' }}>
            <Badge color="blue" variant="filled" size="lg" mb="xs">
              Platform Generation Soal Otomatis
            </Badge>
            <Title order={1} style={{ letterSpacing: '-0.5px' }} mb="xs">
              RAG-AQG (v3.0)
            </Title>
            <Text c="dimmed" size="lg" mb="md">
              Sistem berbasis AI yang mengubah buku digital (PDF) menjadi soal pilihan ganda berkualitas tinggi dengan Taksonomi Bloom dan validasi otomatis 2-layer.
            </Text>
            <Group gap="sm">
              <Button component={Link} href="/documents" leftSection={<IconBook size={18} />} size="md" radius="md">
                Unggah Dokumen PDF
              </Button>
              <Button component={Link} href="/chat" variant="outline" leftSection={<IconMessage2 size={18} />} size="md" radius="md">
                Mulai Chat & Generate
              </Button>
            </Group>
          </Box>
          <ThemeIcon size={80} radius="xl" variant="light" color="blue">
            <IconSparkles size={44} />
          </ThemeIcon>
        </Group>
      </Paper>

      <Title order={3}>Navigasi Fitur Utama</Title>

      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg">
        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <ThemeIcon size="xl" radius="md" color="blue" mb="md">
            <IconBook size={24} />
          </ThemeIcon>
          <Text fw={700} size="lg" mb="xs">
            1. Manajemen Dokumen
          </Text>
          <Text size="sm" c="dimmed" mb="lg">
            Unggah file PDF materi pelajaran (PJOK, IPAS, PKN). Sistem akan mengekstrak teks, memilah bab, dan membuat chunking pedagogis otomatis (PAC).
          </Text>
          <Button component={Link} href="/documents" variant="light" rightSection={<IconArrowRight size={16} />} fullWidth radius="md">
            Buka Dokumen
          </Button>
        </Card>

        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <ThemeIcon size="xl" radius="md" color="cyan" mb="md">
            <IconMessage2 size={24} />
          </ThemeIcon>
          <Text fw={700} size="lg" mb="xs">
            2. AQG Chatbot
          </Text>
          <Text size="sm" c="dimmed" mb="lg">
            Berinteraksi langsung dengan chatbot RAG. Minta pembuat soal berdasarkan bab atau level Taksonomi Bloom tertentu secara gratis halusinasi.
          </Text>
          <Button component={Link} href="/chat" variant="light" color="cyan" rightSection={<IconArrowRight size={16} />} fullWidth radius="md">
            Buka Chatbot
          </Button>
        </Card>

        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <ThemeIcon size="xl" radius="md" color="teal" mb="md">
            <IconQuestionMark size={24} />
          </ThemeIcon>
          <Text fw={700} size="lg" mb="xs">
            3. Bank & Audit Soal
          </Text>
          <Text size="sm" c="dimmed" mb="lg">
            Lihat daftar soal yang telah dihasilkan, kunci jawaban, penjelasan, serta riwayat audit validasi (Grounding Score & LLM-as-Judge).
          </Text>
          <Button component={Link} href="/questions" variant="light" color="teal" rightSection={<IconArrowRight size={16} />} fullWidth radius="md">
            Lihat Bank Soal
          </Button>
        </Card>
      </SimpleGrid>

      <Paper p="lg" radius="md" withBorder mt="md">
        <Title order={4} mb="sm">
          Alur Validasi Dua-Lapis (2-Layer Self-Refinement)
        </Title>
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
          <Group align="flex-start" wrap="nowrap">
            <ThemeIcon size="md" radius="xl" color="blue">
              1
            </ThemeIcon>
            <Box>
              <Text fw={600} size="sm">
                Lapis 1: Cosine Similarity Grounding
              </Text>
              <Text size="xs" c="dimmed">
                Mengukur tingkat kesamaan vektor antara soal+jawaban dengan materi sumber (Ambatan Grounding &ge; 0.75).
              </Text>
            </Box>
          </Group>

          <Group align="flex-start" wrap="nowrap">
            <ThemeIcon size="md" radius="xl" color="teal">
              2
            </ThemeIcon>
            <Box>
              <Text fw={600} size="sm">
                Lapis 2: Rubrik Pedagogis LLM-as-Judge
              </Text>
              <Text size="xs" c="dimmed">
                Mengevaluasi kejelasan pertanyaan, kebenaran kunci jawaban, kelayakan opsi pengecoh, dan Taksonomi Bloom.
              </Text>
            </Box>
          </Group>
        </SimpleGrid>
      </Paper>
    </Stack>
  );
}
