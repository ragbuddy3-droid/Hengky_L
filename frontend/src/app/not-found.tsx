'use client';

import { Title, Text, Button, Container, Group } from '@mantine/core';
import Link from 'next/link';

export default function NotFound() {
  return (
    <Container py="xl" style={{ textAlign: 'center' }}>
      <Title order={1} mb="sm">404 - Halaman Tidak Ditemukan</Title>
      <Text c="dimmed" mb="lg">
        Halaman yang Anda cari tidak dapat ditemukan.
      </Text>
      <Group justify="center">
        <Button component={Link} href="/">
          Kembali ke Dashboard
        </Button>
      </Group>
    </Container>
  );
}
