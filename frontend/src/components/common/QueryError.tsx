'use client';

import { Alert, Button } from '@mantine/core';
import { IconAlertTriangle, IconRefresh } from '@tabler/icons-react';

export function QueryError({ error, onRetry, title = 'Gagal memuat data' }: { error: Error; onRetry?: () => void; title?: string }) {
  return (
    <Alert color="red" variant="light" title={title} icon={<IconAlertTriangle size={18} aria-hidden />}>
      {error.message}
      {onRetry && (
        <Button
          display="block"
          mt="sm"
          size="xs"
          variant="white"
          color="red"
          leftSection={<IconRefresh size={14} aria-hidden />}
          onClick={onRetry}
        >
          Coba lagi
        </Button>
      )}
    </Alert>
  );
}
