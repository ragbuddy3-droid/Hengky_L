'use client';

import { useState, useEffect, useCallback, Suspense } from 'react';
import {
  AppShell, Group, Title, Text, NavLink, ActionIcon,
  useMantineColorScheme, Box, Container, Divider,
  Button, ScrollArea, Tooltip, Loader, ThemeIcon
} from '@mantine/core';
import {
  IconBook, IconMessage2, IconQuestionMark, IconSun, IconMoon,
  IconCpu, IconSparkles, IconPlus, IconTrash
} from '@tabler/icons-react';
import Link from 'next/link';
import { usePathname, useSearchParams, useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { ChatSession } from '@/types/chat';

function NavbarChatList({ pathname }: { pathname: string }) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const activeSessionId = searchParams.get('session_id');

  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);

  const fetchChatSessions = useCallback(async () => {
    try {
      setLoadingSessions(true);
      const list = await api.listChatSessions();
      setChatSessions(list);
    } catch (err) {
      console.error('Failed to load chat sessions for navbar:', err);
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  useEffect(() => {
    fetchChatSessions();

    const handleSessionsChanged = () => {
      fetchChatSessions();
    };

    window.addEventListener('chat-sessions-changed', handleSessionsChanged);
    return () => {
      window.removeEventListener('chat-sessions-changed', handleSessionsChanged);
    };
  }, [fetchChatSessions]);

  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Apakah Anda yakin ingin menghapus sesi chat ini?')) return;

    try {
      await api.deleteChatSession(sessionId);
      window.dispatchEvent(new Event('chat-sessions-changed'));
      if (activeSessionId === sessionId) {
        router.push('/chat');
      }
    } catch (err: any) {
      alert(err.message || 'Gagal menghapus sesi chat.');
    }
  };

  return (
    <ScrollArea style={{ flex: 1, minHeight: '180px' }}>
      {loadingSessions && chatSessions.length === 0 ? (
        <Group justify="center" py="xs">
          <Loader size="xs" />
        </Group>
      ) : chatSessions.length === 0 ? (
        <Text size="xs" c="dimmed" ta="center" py="md">
          Belum ada riwayat chat.
        </Text>
      ) : (
        <Box>
          {chatSessions.map((session, idx) => {
            const isActive = pathname.startsWith('/chat') && activeSessionId === session.id;
            const snippet = session.last_message_snippet || `Chat #${chatSessions.length - idx}`;
            const docName = session.document_filename ? ` (${session.document_filename})` : '';

            return (
              <Box
                key={session.id}
                style={{
                  position: 'relative',
                  marginBottom: '4px',
                  borderRadius: '8px',
                  overflow: 'hidden'
                }}
              >
                <NavLink
                  component={Link}
                  href={`/chat?session_id=${session.id}`}
                  label={
                    <Text size="xs" fw={isActive ? 700 : 500} truncate style={{ paddingRight: '20px' }}>
                      {snippet}
                    </Text>
                  }
                  description={
                    <Text size="xs" c="dimmed" style={{ fontSize: '10px' }} truncate>
                      {session.created_at || 'Baru saja'}{docName}
                    </Text>
                  }
                  leftSection={<IconMessage2 size={16} color={isActive ? 'var(--mantine-color-blue-6)' : undefined} />}
                  active={isActive}
                  variant={isActive ? 'filled' : 'subtle'}
                  style={{ borderRadius: '8px', paddingRight: '30px' }}
                />
                <ActionIcon
                  size="xs"
                  variant="subtle"
                  color="red"
                  onClick={(e) => handleDeleteSession(session.id, e)}
                  style={{
                    position: 'absolute',
                    right: '6px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    zIndex: 2,
                  }}
                  aria-label="Hapus Chat"
                >
                  <IconTrash size={13} />
                </ActionIcon>
              </Box>
            );
          })}
        </Box>
      )}
    </ScrollArea>
  );
}

export default function AppShellLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();
  const isDark = colorScheme === 'dark';

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 280, breakpoint: 'sm' }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="xs">
            <ThemeIcon size="md" radius="md" color="blue" variant="light">
              <IconCpu size={20} />
            </ThemeIcon>
            <Title order={4} style={{ letterSpacing: '-0.5px' }}>
              Automatic Question Generator
            </Title>
          </Group>

          <Group>
            <ActionIcon
              variant="default"
              onClick={() => toggleColorScheme()}
              size="lg"
              radius="md"
              aria-label="Toggle color scheme"
            >
              {isDark ? <IconSun size={18} color="#fcc419" /> : <IconMoon size={18} color="#4c6ef5" />}
            </ActionIcon>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="md" style={{ display: 'flex', flexDirection: 'column' }}>
        <Text size="xs" fw={700} c="dimmed" mb="xs" style={{ textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          Menu Utama
        </Text>

        <NavLink
          component={Link}
          href="/"
          label="Dashboard"
          leftSection={<IconSparkles size={20} stroke={1.5} />}
          active={pathname === '/'}
          variant="filled"
          mb={4}
          style={{ borderRadius: '8px' }}
        />

        <NavLink
          component={Link}
          href="/documents"
          label="Manajemen Dokumen"
          leftSection={<IconBook size={20} stroke={1.5} />}
          active={pathname.startsWith('/documents')}
          variant="filled"
          mb={4}
          style={{ borderRadius: '8px' }}
        />

        <NavLink
          component={Link}
          href="/questions"
          label="Bank & Audit Soal"
          leftSection={<IconQuestionMark size={20} stroke={1.5} />}
          active={pathname.startsWith('/questions')}
          variant="filled"
          mb={4}
          style={{ borderRadius: '8px' }}
        />

        <Divider my="sm" />

        {/* Chat Section in Navbar */}
        <Group justify="space-between" mb="xs">
          <Text size="xs" fw={700} c="dimmed" style={{ textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Percakapan Chat
          </Text>
          <Tooltip label="Chat Baru (Draft Baru)">
            <Button
              component={Link}
              href="/chat"
              size="xs"
              variant="light"
              color="blue"
              leftSection={<IconPlus size={14} />}
              style={{ borderRadius: '6px' }}
            >
              Chat Baru
            </Button>
          </Tooltip>
        </Group>

        {/* List Chat History Wrapped in Suspense */}
        <Suspense fallback={<Text size="xs" c="dimmed" ta="center" py="sm">Memuat...</Text>}>
          <NavbarChatList pathname={pathname} />
        </Suspense>

        <Box style={{ marginTop: 'auto', paddingTop: '0.75rem', borderTop: '1px solid var(--mantine-color-default-border)' }}>
          <Text size="xs" c="dimmed" ta="center">
            Python FastAPI + Next.js (Bun)
          </Text>
        </Box>
      </AppShell.Navbar>

      <AppShell.Main style={{ height: 'calc(100vh - 60px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Container size="xl" py={pathname.startsWith('/chat') ? 0 : 'sm'} style={{ flex: 1, display: 'flex', flexDirection: 'column', width: '100%', minHeight: 0, overflow: pathname.startsWith('/chat') ? 'hidden' : 'auto' }}>
          {children}
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}
