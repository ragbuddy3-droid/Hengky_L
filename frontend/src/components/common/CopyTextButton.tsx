'use client';

import { ActionIcon, CopyButton, Tooltip } from '@mantine/core';
import { IconCheck, IconCopy } from '@tabler/icons-react';

export function CopyTextButton({ value, label = 'Salin' }: { value: string; label?: string }) {
  return (
    <CopyButton value={value} timeout={1500}>
      {({ copied, copy }) => (
        <Tooltip label={copied ? 'Tersalin' : label}>
          <ActionIcon color={copied ? 'green' : 'gray'} onClick={copy} aria-label={label}>
            {copied ? <IconCheck size={16} aria-hidden /> : <IconCopy size={16} aria-hidden />}
          </ActionIcon>
        </Tooltip>
      )}
    </CopyButton>
  );
}
