import { Box, Text } from '@mantine/core';

/** Blok berlabel kecil untuk isi detail soal. */
export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Box>
      <Text size="xs" fw={600} c="dimmed" tt="uppercase" mb={4}>
        {title}
      </Text>
      {children}
    </Box>
  );
}
