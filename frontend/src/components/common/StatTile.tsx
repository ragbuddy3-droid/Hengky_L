import { Paper, Text } from '@mantine/core';

export function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Paper p="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text fz={24} fw={700} mt={4}>
        {value}
      </Text>
      {hint && (
        <Text size="xs" c="dimmed">
          {hint}
        </Text>
      )}
    </Paper>
  );
}
