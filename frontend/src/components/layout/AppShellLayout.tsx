'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { AppShell, Box, Burger, Button, Divider, Group, NavLink, ScrollArea, Text } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconBooks, IconListCheck, IconMessageCircle, IconPlus } from '@tabler/icons-react';
import { LogoMark } from '@/components/brand/LogoMark';
import { AccountMenu } from './AccountMenu';
import { NavbarSessions } from './NavbarSessions';

const NAV_ITEMS = [
  { href: '/chat', label: 'Chat', icon: IconMessageCircle },
  { href: '/documents', label: 'Dokumen', icon: IconBooks },
  { href: '/questions', label: 'Bank Soal', icon: IconListCheck },
];

function Brand() {
  return (
    <Group gap="xs" wrap="nowrap">
      <LogoMark size={34} />
      <Box>
        <Text fw={700} lh={1.1}>
          Soalnya
        </Text>
        <Text size="xs" c="dimmed" lh={1.1}>
          Soal otomatis dari buku
        </Text>
      </Box>
    </Group>
  );
}

export function AppShellLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [opened, { toggle, close }] = useDisclosure();

  // Tutup drawer navigasi mobile setiap kali pindah halaman.
  useEffect(() => close(), [pathname, close]);

  return (
    <>
      <a href="#main-content" className="skip-link">
        Lewati ke konten utama
      </a>
      <AppShell
        header={{ height: { base: 56, sm: 0 } }}
        navbar={{ width: 272, breakpoint: 'sm', collapsed: { mobile: !opened } }}
        padding={0}
      >
        <AppShell.Header hiddenFrom="sm" px="md">
          <Group h="100%" justify="space-between">
            <Brand />
            <Burger opened={opened} onClick={toggle} size="sm" aria-label={opened ? 'Tutup menu navigasi' : 'Buka menu navigasi'} />
          </Group>
        </AppShell.Header>

        <AppShell.Navbar p="md" aria-label="Navigasi utama">
          <AppShell.Section visibleFrom="sm" mb="md">
            <Brand />
          </AppShell.Section>

          <AppShell.Section>
            <Button
              component={Link}
              href="/chat"
              fullWidth
              leftSection={<IconPlus size={16} aria-hidden />}
              mb="sm"
            >
              Chat Baru
            </Button>
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
              <NavLink
                key={href}
                component={Link}
                href={href}
                label={label}
                leftSection={<Icon size={18} stroke={1.75} aria-hidden />}
                active={pathname.startsWith(href)}
                variant="light"
                style={{ borderRadius: 'var(--mantine-radius-md)' }}
                mb={2}
              />
            ))}
          </AppShell.Section>

          <Divider my="md" />

          <Text size="xs" fw={600} c="dimmed" tt="uppercase" mb="xs" px="xs">
            Riwayat Chat
          </Text>
          <AppShell.Section grow component={ScrollArea} mx="-xs" px="xs">
            <NavbarSessions />
          </AppShell.Section>

          <AppShell.Section pt="sm" mt="sm" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }}>
            <AccountMenu />
          </AppShell.Section>
        </AppShell.Navbar>

        <AppShell.Main id="main-content" tabIndex={-1} style={{ outline: 'none' }}>
          {children}
        </AppShell.Main>
      </AppShell>
    </>
  );
}
