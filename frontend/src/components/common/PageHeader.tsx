import { Box, Group, Text, Title } from '@mantine/core';

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <Group justify="space-between" align="flex-start" gap="md" mb="lg">
      <Box>
        <Title order={2} fz={{ base: 22, sm: 26 }}>
          {title}
        </Title>
        {description && (
          <Text c="dimmed" size="sm" mt={4} maw={640}>
            {description}
          </Text>
        )}
      </Box>
      {actions && <Group gap="sm">{actions}</Group>}
    </Group>
  );
}
