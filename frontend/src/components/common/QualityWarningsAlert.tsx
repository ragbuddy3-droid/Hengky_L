import { Alert, List } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';

/** Daftar catatan kualitas soal; tidak dirender bila kosong. */
export function QualityWarningsAlert({ warnings }: { warnings?: string[] | null }) {
  if (!warnings?.length) return null;
  return (
    <Alert color="orange" icon={<IconAlertTriangle size={18} aria-hidden />} title="Catatan kualitas">
      <List size="sm">
        {warnings.map((w) => (
          <List.Item key={w}>{w}</List.Item>
        ))}
      </List>
    </Alert>
  );
}
