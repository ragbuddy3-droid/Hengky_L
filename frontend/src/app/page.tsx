'use client';

import { Title, Text, SimpleGrid, Card, Group, ThemeIcon, Button, Stack, Badge, Paper, Box } from '@mantine/core';
import { IconBook, IconMessage2, IconQuestionMark, IconArrowRight, IconSparkles } from '@tabler/icons-react';
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
              Platform Generasi Soal Otomatis Berbasis RAG
            </Badge>
            <Title order={1} style={{ letterSpacing: '-0.5px' }} mb="xs">
              RAG-AQG (v4.0)
            </Title>
            <Text c="dimmed" size="lg" mb="md">
              Sistem AI cerdas yang mengubah buku digital (PDF) menjadi soal evaluasi esai & isian singkat (C1–C4 SD) berkualitas tinggi dengan Section-Aware Chunking, High-Precision Retrieval, dan Validasi 2-Layer.
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
            Unggah file PDF materi pelajaran. Sistem mengekstrak teks berbasis halaman, memilah struktur bab & heading, serta memotong materi secara Section-Aware.
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
            Berinteraksi langsung dengan chatbot RAG. Minta pembuatan soal evaluasi berdasarkan bab materi dan target kognitif Bloom C1–C4 jenjang SD.
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
            Tinjau paket soal esai & isian singkat, kunci jawaban, penjelasan edukatif, rubrik penskoran, serta audit jejak 4 tahap generasi dan validasi.
          </Text>
          <Button component={Link} href="/questions" variant="light" color="teal" rightSection={<IconArrowRight size={16} />} fullWidth radius="md">
            Lihat Bank Soal
          </Button>
        </Card>
      </SimpleGrid>

      <Paper p="lg" radius="md" withBorder mt="md">
        <Title order={4} mb="sm">
          Alur Validasi Dua-Lapis (2-Layer Guardrails)
        </Title>
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
          <Group align="flex-start" wrap="nowrap">
            <ThemeIcon size="md" radius="xl" color="blue">
              1
            </ThemeIcon>
            <Box>
              <Text fw={600} size="sm">
                Lapis 1: Fast-Reject Grounding Similarity
              </Text>
              <Text size="xs" c="dimmed">
                Menyaring cepat kandidat soal dengan kemiripan vektor embedding rendah (&lt; 0.40) untuk direvisi langsung tanpa memboroskan token juri.
              </Text>
            </Box>
          </Group>

          <Group align="flex-start" wrap="nowrap">
            <ThemeIcon size="md" radius="xl" color="teal">
              2
            </ThemeIcon>
            <Box>
              <Text fw={600} size="sm">
                Lapis 2: LLM-as-Judge 5 Aspek Pedagogis SD
              </Text>
              <Text size="xs" c="dimmed">
                Mengevaluasi kesesuaian Bloom C1–C4, stimulus skenario kontekstual nyata, bahasa ramah anak SD, keterjawaban materi, dan keselarasan jawaban.
              </Text>
            </Box>
          </Group>
        </SimpleGrid>
      </Paper>
    </Stack>
  );
}
