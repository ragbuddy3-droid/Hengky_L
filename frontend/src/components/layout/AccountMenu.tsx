'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  ActionIcon,
  Avatar,
  Box,
  Button,
  Group,
  Menu,
  Paper,
  Skeleton,
  Text,
  Tooltip,
  UnstyledButton,
  useMantineColorScheme,
  type MantineColorScheme,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconCheck,
  IconDeviceDesktop,
  IconLogout,
  IconMoon,
  IconSelector,
  IconSettings,
  IconSun,
  IconUserCircle,
} from '@tabler/icons-react';
import { SettingsModal } from '@/components/settings/SettingsModal';
import { useLogout, useMe } from '@/hooks/useAuth';
import type { User } from '@/types/auth';

const THEME_OPTIONS: { value: MantineColorScheme; label: string; icon: typeof IconSun }[] = [
  { value: 'light', label: 'Terang', icon: IconSun },
  { value: 'dark', label: 'Gelap', icon: IconMoon },
  { value: 'auto', label: 'Sistem', icon: IconDeviceDesktop },
];

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase() || '?';
}

function UserMenu({ user, onOpenSettings }: { user: User; onOpenSettings: () => void }) {
  const router = useRouter();
  const logout = useLogout();
  const { colorScheme, setColorScheme } = useMantineColorScheme();

  const handleLogout = () =>
    logout.mutate(undefined, {
      onSuccess: () => {
        notifications.show({ message: 'Anda telah keluar.' });
        router.push('/chat');
      },
      onError: (err) => notifications.show({ color: 'red', title: 'Gagal keluar', message: err.message }),
    });

  return (
    <Menu position="top-start" width="target" withinPortal shadow="md">
      <Menu.Target>
        <UnstyledButton
          w="100%"
          p="xs"
          aria-label={`Menu akun ${user.name}`}
          style={{ borderRadius: 'var(--mantine-radius-md)' }}
          className="hover-chip"
        >
          <Group gap="sm" wrap="nowrap">
            <Avatar color="indigo" radius="xl" size={36}>
              {initials(user.name)}
            </Avatar>
            <Box style={{ flex: 1, minWidth: 0 }}>
              <Text size="sm" fw={600} truncate>
                {user.name}
              </Text>
              <Text size="xs" c="dimmed" truncate>
                {user.email}
              </Text>
            </Box>
            <IconSelector size={16} aria-hidden style={{ flexShrink: 0, color: 'var(--mantine-color-dimmed)' }} />
          </Group>
        </UnstyledButton>
      </Menu.Target>

      <Menu.Dropdown>
        <Menu.Item leftSection={<IconSettings size={16} aria-hidden />} onClick={onOpenSettings}>
          Pengaturan
        </Menu.Item>
        <Menu.Divider />
        <Menu.Label>Tema</Menu.Label>
        {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
          <Menu.Item
            key={value}
            leftSection={<Icon size={16} aria-hidden />}
            rightSection={colorScheme === value ? <IconCheck size={14} aria-hidden /> : null}
            aria-checked={colorScheme === value}
            role="menuitemradio"
            closeMenuOnClick={false}
            onClick={() => setColorScheme(value)}
          >
            {label}
          </Menu.Item>
        ))}
        <Menu.Divider />
        <Menu.Item color="red" leftSection={<IconLogout size={16} aria-hidden />} onClick={handleLogout} disabled={logout.isPending}>
          Keluar
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

function GuestCard({ onOpenSettings }: { onOpenSettings: () => void }) {
  const pathname = usePathname();
  const next = pathname && pathname !== '/chat' ? `?next=${encodeURIComponent(pathname)}` : '';

  return (
    <Paper p="sm" radius="md" bg="var(--mantine-color-default-hover)" withBorder={false}>
      <Group justify="space-between" wrap="nowrap" mb="xs">
        <Group gap="xs" wrap="nowrap">
          <IconUserCircle size={20} stroke={1.75} aria-hidden style={{ color: 'var(--mantine-color-dimmed)' }} />
          <Text size="sm" fw={600}>
            Mode tamu
          </Text>
        </Group>
        <Tooltip label="Pengaturan tampilan">
          <ActionIcon onClick={onOpenSettings} aria-label="Pengaturan tampilan">
            <IconSettings size={18} aria-hidden />
          </ActionIcon>
        </Tooltip>
      </Group>
      <Text size="xs" c="dimmed" mb="sm">
        Masuk agar dokumen dan soal tersimpan permanen.
      </Text>
      <Group gap="xs" grow>
        <Button component={Link} href={`/login${next}`} size="xs">
          Masuk
        </Button>
        <Button component={Link} href={`/register${next}`} size="xs" variant="default">
          Daftar
        </Button>
      </Group>
    </Paper>
  );
}

/** Kartu akun di bagian bawah sidebar: menu akun untuk pengguna login, ajakan masuk untuk tamu. */
export function AccountMenu() {
  const { user, isPending } = useMe();
  const [settingsOpened, setSettingsOpened] = useState(false);
  const openSettings = () => setSettingsOpened(true);

  let content: React.ReactNode;
  if (isPending) content = <Skeleton h={52} radius="md" />;
  else if (user) content = <UserMenu user={user} onOpenSettings={openSettings} />;
  else content = <GuestCard onOpenSettings={openSettings} />;

  return (
    <>
      {content}
      <SettingsModal opened={settingsOpened} onClose={() => setSettingsOpened(false)} />
    </>
  );
}
