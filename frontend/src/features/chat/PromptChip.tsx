'use client';

import { UnstyledButton, type UnstyledButtonProps } from '@mantine/core';

/** Chip contoh permintaan (tombol pil) — punya ring fokus bawaan Mantine. */
export function PromptChip({
  children,
  onClick,
  disabled,
  size = 'xs',
  ...props
}: { children: string; onClick: () => void; disabled?: boolean; size?: 'xs' | 'sm' } & UnstyledButtonProps) {
  return (
    <UnstyledButton
      onClick={onClick}
      disabled={disabled}
      px="sm"
      py={size === 'sm' ? 6 : 4}
      fz={size}
      bd="1px solid var(--mantine-color-default-border)"
      className="hover-chip"
      style={{ borderRadius: 999, opacity: disabled ? 0.5 : 1 }}
      {...props}
    >
      {children}
    </UnstyledButton>
  );
}
