'use client';

import { useState, useEffect, useRef, Suspense } from 'react';
import {
  Title, Text, Stack, Group, Select, Textarea, ActionIcon,
  Button, Badge, Loader, Alert, Chip, Card, Box, Divider
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconSend, IconMessage2, IconSparkles, IconCheck, IconAlertCircle,
  IconListCheck, IconBook, IconRefresh, IconHelpCircle, IconPlus
} from '@tabler/icons-react';
import { useSearchParams, useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { Document } from '@/types/document';
import { ChatMessage } from '@/types/chat';
import { Question } from '@/types/question';

function ChatContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const urlSessionId = searchParams.get('session_id');

  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);

  // Active Session ID (null means New Draft Session)
  const [sessionId, setSessionId] = useState<string | null>(urlSessionId);

  // Messages & Questions State
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const [inputContent, setInputContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [fetchingDocs, setFetchingDocs] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load available ready documents on mount
  useEffect(() => {
    async function loadDocs() {
      try {
        setFetchingDocs(true);
        const docs = await api.listDocuments();
        const readyDocs = docs.filter((d) => d.status === 'ready');
        setDocuments(readyDocs);
        if (readyDocs.length > 0 && !selectedDocId) {
          setSelectedDocId(readyDocs[0].id);
        }
      } catch (err: any) {
        notifications.show({
          title: 'Gagal Memuat Dokumen',
          message: 'Pastikan backend FastAPI sudah berjalan.',
          color: 'red',
        });
      } finally {
        setFetchingDocs(false);
      }
    }
    loadDocs();
  }, []);

  // Sync state when URL session_id changes
  useEffect(() => {
    setSessionId(urlSessionId);

    if (urlSessionId) {
      loadExistingSession(urlSessionId);
    } else {
      // Draft mode (New Chat)
      setMessages([
        {
          id: 'welcome',
          role: 'assistant',
          content: 'Halo! Saya asisten AQG RAG. Silakan pilih dokumen acuan di atas dan kirimkan instruksi pembuatan soal (contoh: "Buatkan 5 soal esai C4 bab 2").',
        },
      ]);
      setQuestions([]);
    }
  }, [urlSessionId]);

  // Load existing session messages and questions
  const loadExistingSession = async (sId: string) => {
    try {
      const msgs = await api.getChatMessages(sId);
      if (msgs.length === 0) {
        setMessages([
          {
            id: 'welcome',
            role: 'assistant',
            content: 'Halo! Sesi ini siap digunakan. Kirimkan pesan untuk mulai membuat soal.',
          },
        ]);
      } else {
        setMessages(msgs);
      }
      fetchQuestions(sId);
    } catch (err: any) {
      notifications.show({
        title: 'Gagal Memuat Sesi Chat',
        message: err.message,
        color: 'red',
      });
    }
  };

  // Load questions for current session
  const fetchQuestions = async (sId: string) => {
    try {
      setLoadingQuestions(true);
      const qList = await api.listQuestions(sId);
      setQuestions(qList);
    } catch (err: any) {
      console.error('Failed to load questions:', err);
    } finally {
      setLoadingQuestions(false);
    }
  };

  // Scroll chat to bottom when messages update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Poll for background generation response & question updates
  useEffect(() => {
    if (!sessionId) return;

    const hasGeneratingMsg = messages.some((m) => m.content.includes('Sedang membuat'));
    if (!hasGeneratingMsg) return;

    const interval = setInterval(async () => {
      try {
        const history = await api.getChatMessages(sessionId);
        if (history.length > messages.length) {
          setMessages(history);
          fetchQuestions(sessionId);
          window.dispatchEvent(new Event('chat-sessions-changed'));
        }
      } catch {
        // ignore poll errors
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [sessionId, messages]);

  const handleSendMessage = async () => {
    if (!inputContent.trim() || loading || !selectedDocId) {
      if (!selectedDocId) {
        notifications.show({
          title: 'Pilih Dokumen',
          message: 'Silakan pilih dokumen acuan terlebih dahulu.',
          color: 'yellow',
        });
      }
      return;
    }

    const userText = inputContent.trim();
    setInputContent('');

    let currentSessionId = sessionId;

    try {
      setLoading(true);

      // Lazy Session Creation: Create DB session on first message if in draft mode
      if (!currentSessionId) {
        const newSession = await api.createChatSession(selectedDocId);
        currentSessionId = newSession.id;
        setSessionId(currentSessionId);
        
        // Notify Navbar of new session
        window.dispatchEvent(new Event('chat-sessions-changed'));
      }

      // Optimistic UI update
      const tempUserMsg: ChatMessage = {
        id: `temp-${Date.now()}`,
        role: 'user',
        content: userText,
      };
      setMessages((prev) => [...prev, tempUserMsg]);

      // Send message to backend
      const botMsg = await api.sendChatMessage(currentSessionId, userText);
      setMessages((prev) => [...prev, botMsg]);

      // Update URL silently without full reload
      router.push(`/chat?session_id=${currentSessionId}`);
      window.dispatchEvent(new Event('chat-sessions-changed'));

    } catch (err: any) {
      notifications.show({
        title: 'Gagal Mengirim Pesan',
        message: err.message || 'Terjadi kesalahan.',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleStartNewChatDraft = () => {
    router.push('/chat');
  };

  const setPromptSuggestion = (prompt: string) => {
    setInputContent(prompt);
  };

  const renderBloomBadge = (bloom: string) => {
    const bUpper = (bloom || '').toUpperCase();
    if (bUpper.includes('C1')) return <Badge color="gray" variant="filled" size="xs">C1 - Mengingat</Badge>;
    if (bUpper.includes('C2')) return <Badge color="blue" variant="filled" size="xs">C2 - Memahami</Badge>;
    if (bUpper.includes('C3')) return <Badge color="cyan" variant="filled" size="xs">C3 - Mengaplikasikan</Badge>;
    if (bUpper.includes('C4')) return <Badge color="indigo" variant="filled" size="xs">C4 - Menganalisis</Badge>;
    if (bUpper.includes('C5')) return <Badge color="violet" variant="filled" size="xs">C5 - Mengevaluasi</Badge>;
    if (bUpper.includes('C6')) return <Badge color="grape" variant="filled" size="xs">C6 - Mencipta</Badge>;
    return <Badge color="teal" variant="filled" size="xs">{bloom || 'C4'}</Badge>;
  };

  const renderStatusBadge = (status: string) => {
    if (status === 'final') return <Badge color="green" variant="light" size="xs">Lolos Validasi</Badge>;
    return <Badge color="yellow" variant="light" size="xs">Perlu Tinjauan</Badge>;
  };

  return (
    <Box style={{ flex: 1, height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {documents.length === 0 && !fetchingDocs && (
        <Alert color="yellow" icon={<IconAlertCircle size={18} />} mb="xs" style={{ flexShrink: 0 }}>
          Belum ada dokumen berselisih status <strong>Ready</strong>. Silakan unggah dokumen PDF di halaman <strong>Manajemen Dokumen</strong> terlebih dahulu.
        </Alert>
      )}

      {/* Main 2-Column Side-by-Side Flex Layout */}
      <Box style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'row', gap: '16px', overflow: 'hidden' }}>
        
        {/* LEFT COLUMN: CHAT STREAM & INPUT AREA (Flex: 7) */}
        <Box style={{ flex: '7 1 0%', display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, minWidth: 0 }}>
          
          {/* Top Integrated Header Row (Fixed Top) */}
          <Box style={{ flexShrink: 0, paddingBottom: '10px', borderBottom: '1px solid var(--mantine-color-default-border)' }}>
            <Group justify="space-between" align="center">
              <Group gap="xs">
                <Box
                  style={{
                    background: 'linear-gradient(135deg, #228be6 0%, #15aabf 100%)',
                    padding: '6px 10px',
                    borderRadius: '8px',
                    color: '#fff',
                    display: 'flex',
                    alignItems: 'center',
                  }}
                >
                  <IconMessage2 size={18} />
                </Box>
                <div>
                  <Group gap="xs">
                    <Text fw={700} size="sm">AQG Chatbot</Text>
                    {sessionId ? (
                      <Badge size="xs" variant="outline" color="blue">Sesi Aktif</Badge>
                    ) : (
                      <Badge size="xs" variant="dot" color="teal">Draft Baru</Badge>
                    )}
                  </Group>
                  <Text size="xs" c="dimmed" style={{ fontSize: '11px' }}>Generasi Soal Otomatis Berbasis RAG</Text>
                </div>
              </Group>

              {/* Document Selector + New Chat Button */}
              <Group gap="xs">
                <Select
                  placeholder="Pilih Dokumen Acuan"
                  value={selectedDocId}
                  onChange={(val) => setSelectedDocId(val)}
                  data={documents.map((d) => ({ value: d.id, label: `${d.filename} (${d.subject})` }))}
                  style={{ width: '220px' }}
                  disabled={fetchingDocs || documents.length === 0}
                  size="xs"
                />
                <Button
                  size="xs"
                  variant="light"
                  color="blue"
                  leftSection={<IconPlus size={14} />}
                  onClick={handleStartNewChatDraft}
                >
                  Chat Baru
                </Button>
              </Group>
            </Group>
          </Box>

          {/* Messages Stream (Independent Scrollable Middle) */}
          <Box style={{ flex: 1, minHeight: 0, overflowY: 'auto', paddingRight: '8px', paddingTop: '10px', paddingBottom: '10px' }}>
            <Stack gap="md">
              {messages.map((msg) => (
                <Group
                  key={msg.id}
                  justify={msg.role === 'user' ? 'flex-end' : 'flex-start'}
                  align="flex-start"
                >
                  <Box
                    p="sm"
                    px="md"
                    style={{
                      maxWidth: '85%',
                      borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                      backgroundColor:
                        msg.role === 'user'
                          ? 'var(--mantine-color-blue-filled)'
                          : 'var(--mantine-color-default-hover)',
                      color: msg.role === 'user' ? '#fff' : 'inherit',
                      boxShadow: msg.role === 'user' ? '0 2px 6px rgba(34, 139, 230, 0.25)' : 'none',
                      border: msg.role === 'assistant' ? '1px solid var(--mantine-color-default-border)' : 'none',
                    }}
                  >
                    <Group gap="xs" mb={4}>
                      <Text size="xs" fw={700} opacity={0.85}>
                        {msg.role === 'user' ? 'Anda' : 'AQG Assistant'}
                      </Text>
                      {msg.role === 'assistant' && (
                        <Badge size="xs" variant="light" color="cyan">
                          RAG AI
                        </Badge>
                      )}
                    </Group>
                    <Text size="sm" style={{ whiteSpace: 'pre-wrap', lineHeight: '1.5' }}>
                      {msg.content}
                    </Text>
                  </Box>
                </Group>
              ))}
              <div ref={messagesEndRef} />
            </Stack>
          </Box>

          {/* Input Form Area (Always Fixed at Bottom) */}
          <Box style={{ flexShrink: 0, paddingTop: '8px', borderTop: '1px solid var(--mantine-color-default-border)' }}>
            <Group gap="xs" mb="xs">
              <Text size="xs" c="dimmed" style={{ fontSize: '11px' }}>Contoh Perintah Cepat:</Text>
              <Chip size="xs" variant="outline" onClick={() => setPromptSuggestion('Buatkan 5 soal esai C4 bab 2')}>
                Buatkan 5 soal esai C4 bab 2
              </Chip>
              <Chip size="xs" variant="outline" onClick={() => setPromptSuggestion('Buatkan 3 soal isian singkat C2 bab 1')}>
                Buatkan 3 soal isian singkat C2 bab 1
              </Chip>
              <Chip size="xs" variant="outline" onClick={() => setPromptSuggestion('Buatkan 4 soal esai C3 bab 3')}>
                Buatkan 4 soal esai C3 bab 3
              </Chip>
            </Group>

            <Group align="flex-end" gap="xs">
              <Textarea
                placeholder="Tuliskan permintaan soal Anda di sini... (Tekan Enter untuk kirim)"
                value={inputContent}
                onChange={(e) => setInputContent(e.currentTarget.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage();
                  }
                }}
                minRows={2}
                maxRows={3}
                style={{ flex: 1 }}
                disabled={loading}
              />
              <Button
                onClick={handleSendMessage}
                loading={loading}
                disabled={!inputContent.trim()}
                radius="md"
                size="md"
                leftSection={<IconSend size={18} />}
              >
                Kirim
              </Button>
            </Group>
          </Box>
        </Box>

        {/* RIGHT COLUMN: GENERATED QUESTIONS LIST PANEL (Flex: 5) */}
        <Box
          style={{
            flex: '5 1 0%',
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            minHeight: 0,
            minWidth: 0,
            borderLeft: '1px solid var(--mantine-color-default-border)',
            paddingLeft: '16px'
          }}
        >
          {/* Top Header Row (Fixed Top) */}
          <Box style={{ flexShrink: 0, paddingBottom: '10px', borderBottom: '1px solid var(--mantine-color-default-border)' }}>
            <Group justify="space-between" align="center">
              <Group gap="xs">
                <IconListCheck size={20} color="var(--mantine-color-teal-6)" />
                <Text fw={700} size="sm">Daftar Soal Terbentuk ({questions.length})</Text>
              </Group>
              <ActionIcon
                variant="light"
                size="xs"
                color="blue"
                onClick={() => sessionId && fetchQuestions(sessionId)}
                loading={loadingQuestions}
                disabled={!sessionId}
                aria-label="Refresh Daftar Soal"
              >
                <IconRefresh size={14} />
              </ActionIcon>
            </Group>
          </Box>

          {/* Questions List Stream (Independent Scrollable Middle) */}
          <Box style={{ flex: 1, minHeight: 0, overflowY: 'auto', paddingRight: '4px', paddingTop: '10px', paddingBottom: '10px' }}>
            {loadingQuestions ? (
              <Group justify="center" py="xl">
                <Loader size="sm" />
                <Text size="xs" c="dimmed">Memuat daftar soal...</Text>
              </Group>
            ) : questions.length === 0 ? (
              <Stack align="center" justify="center" style={{ height: '100%' }} gap="xs">
                <IconHelpCircle size={44} color="var(--mantine-color-dimmed)" />
                <Text size="xs" c="dimmed" ta="center" style={{ maxWidth: '240px' }}>
                  Belum ada soal yang terbentuk pada sesi percakapan ini. Gunakan kolom chat di sebelah kiri untuk meminta AI men-generate soal.
                </Text>
              </Stack>
            ) : (
              <Stack gap="sm">
                {questions.map((q, idx) => (
                  <Card key={q.id} shadow="xs" padding="sm" radius="md" withBorder>
                    {/* Header Badges */}
                    <Group justify="space-between" mb="xs">
                      <Group gap="xs">
                        <Badge variant="outline" color="dark" size="xs">
                          Soal #{idx + 1}
                        </Badge>
                        <Badge color="blue" size="xs" variant="light">
                          {(q.question_type || 'esai').toUpperCase()}
                        </Badge>
                      </Group>
                      <Group gap="xs">
                        {renderBloomBadge(q.bloom_level)}
                        {renderStatusBadge(q.status)}
                      </Group>
                    </Group>

                    {/* Question Text */}
                    <Text size="sm" fw={600} mb="xs">
                      {q.question_text}
                    </Text>

                    {/* Options if present */}
                    {q.options && typeof q.options === 'object' && (
                      <Box mb="xs" pl="xs" style={{ borderLeft: '2px solid var(--mantine-color-blue-4)' }}>
                        {Object.entries(q.options).map(([key, val]) => (
                          <Text key={key} size="xs" c="dimmed">
                            <strong>{key}.</strong> {String(val)}
                          </Text>
                        ))}
                      </Box>
                    )}

                    {/* Answer Key */}
                    <Box p="xs" style={{ borderRadius: '6px', backgroundColor: 'var(--mantine-color-teal-light)' }} mb="xs">
                      <Text size="xs" fw={700} c="teal">
                        Kunci Jawaban:
                      </Text>
                      <Text size="xs" c="teal" style={{ whiteSpace: 'pre-wrap' }}>
                        {q.answer_key}
                      </Text>
                    </Box>

                    {/* Explanation */}
                    {q.explanation && (
                      <Box p="xs" style={{ borderRadius: '6px', border: '1px solid var(--mantine-color-default-border)' }} mb="xs">
                        <Text size="xs" fw={700} c="dimmed">
                          Penjelasan:
                        </Text>
                        <Text size="xs" style={{ whiteSpace: 'pre-wrap', lineHeight: '1.4' }}>
                          {q.explanation}
                        </Text>
                      </Box>
                    )}

                    {/* Source Reference */}
                    {q.source_reference && (
                      <Group gap={4}>
                        <IconBook size={12} color="var(--mantine-color-dimmed)" />
                        <Text size="xs" c="dimmed" style={{ fontSize: '11px' }}>
                          Ref: <code>{q.source_reference}</code>
                        </Text>
                      </Group>
                    )}
                  </Card>
                ))}
              </Stack>
            )}
          </Box>
        </Box>

      </Box>
    </Box>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={
      <Group justify="center" py="xl">
        <Loader size="md" />
        <Text size="sm" c="dimmed">Memuat AQG Chatbot...</Text>
      </Group>
    }>
      <ChatContent />
    </Suspense>
  );
}
