import { Paper, Stack, Text, ThemeIcon } from '@mantine/core';

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <Paper p="xl" radius="md" style={{ borderStyle: 'dashed' }}>
      <Stack align="center" gap="xs" py="lg" ta="center">
        <ThemeIcon size={48} radius="xl" variant="light">
          {icon}
        </ThemeIcon>
        <Text fw={600} mt="xs">
          {title}
        </Text>
        {description && (
          <Text size="sm" c="dimmed" maw={420}>
            {description}
          </Text>
        )}
        {action && <Stack mt="sm">{action}</Stack>}
      </Stack>
    </Paper>
  );
}
