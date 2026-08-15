'use client';

import { useState, useEffect } from 'react';
import { Title, Text, Stack, Paper, Group, Badge, Card, Accordion, Loader, Alert, Button, SimpleGrid } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconQuestionMark, IconCheck, IconAlertTriangle, IconShieldCheck, IconRefresh, IconScale, IconFileText } from '@tabler/icons-react';
import { api } from '@/lib/api';
import { Question } from '@/types/question';

export default function QuestionsPage() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedQuestion, setSelectedQuestion] = useState<Question | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const fetchQuestions = async () => {
    try {
      setLoading(true);
      const list = await api.listQuestions();
      setQuestions(list);
    } catch (err: any) {
      notifications.show({
        title: 'Gagal Memuat Soal',
        message: err.message || 'Gagal terhubung ke backend.',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQuestions();
  }, []);

  const handleInspectQuestion = async (id: string) => {
    try {
      setLoadingDetail(true);
      const detail = await api.getQuestionDetail(id);
      setSelectedQuestion(detail);
    } catch (err: any) {
      notifications.show({
        title: 'Gagal Memuat Detail Audit',
        message: err.message,
        color: 'red',
      });
    } finally {
      setLoadingDetail(false);
    }
  };

  const renderBloomColor = (bloom: string) => {
    if (bloom.includes('C1')) return 'blue';
    if (bloom.includes('C2')) return 'cyan';
    if (bloom.includes('C3')) return 'teal';
    if (bloom.includes('C4')) return 'grape';
    if (bloom.includes('C5')) return 'orange';
    return 'red';
  };

  const renderTypeBadge = (qType?: string) => {
    const t = (qType || 'esai').toLowerCase();
    if (t === 'isian_singkat' || t === 'isian singkat') {
      return <Badge color="indigo" variant="filled">Isian Singkat</Badge>;
    }
    return <Badge color="violet" variant="filled">Esai</Badge>;
  };

  const renderOptionsList = (options: Record<string, string> | any) => {
    if (!options) return null;
    
    let entries: [string, string][] = [];
    if (Array.isArray(options) && options.length > 0) {
      entries = options.map((opt) => [opt.label || '?', opt.text || '']);
    } else if (typeof options === 'object' && Object.keys(options).length > 0) {
      entries = Object.entries(options);
    }

    if (entries.length === 0) return null;

    return (
      <Stack gap="xs" my="xs">
        <Text size="xs" fw={600} c="dimmed">Opsi Jawaban (Pilihan Ganda Legacy):</Text>
        {entries.map(([key, val]) => (
          <Paper key={key} p="xs" px="sm" radius="xs" withBorder style={{ backgroundColor: 'var(--mantine-color-body)' }}>
            <Text size="sm">
              <strong style={{ color: 'var(--mantine-color-blue-6)' }}>{key}.</strong> {val}
            </Text>
          </Paper>
        ))}
      </Stack>
    );
  };

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="center">
        <div>
          <Title order={2}>Bank & Audit Validasi Soal Esai & Isian Singkat</Title>
          <Text c="dimmed" size="sm">
            Tinjau seluruh soal esai dan isian singkat yang dihasilkan, kunci jawaban / kriteria rubrik penilaian, konteks chunk materi yang digunakan, serta riwayat audit validasi 2-layer.
          </Text>
        </div>
        <Button variant="light" leftSection={<IconRefresh size={16} />} onClick={fetchQuestions} loading={loading}>
          Refresh
        </Button>
      </Group>

      {loading ? (
        <Group justify="center" py="xl">
          <Loader size="md" />
          <Text size="sm" c="dimmed">Memuat daftar soal...</Text>
        </Group>
      ) : questions.length === 0 ? (
        <Alert color="blue" icon={<IconQuestionMark size={18} />}>
          Belum ada soal yang dihasilkan. Silakan masuk ke halaman <strong>AQG Chatbot</strong> dan minta pembuatan soal esai / isian singkat terlebih dahulu.
        </Alert>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
          {/* Question List Column */}
          <Stack gap="md">
            <Title order={4}>Daftar Soal ({questions.length})</Title>
            {questions.map((q, idx) => (
              <Card
                key={q.id}
                shadow="xs"
                padding="md"
                radius="md"
                withBorder
                style={{
                  cursor: 'pointer',
                  borderColor: selectedQuestion?.id === q.id ? 'var(--mantine-color-blue-6)' : undefined,
                  borderWidth: selectedQuestion?.id === q.id ? '2px' : '1px',
                }}
                onClick={() => handleInspectQuestion(q.id)}
              >
                <Group justify="space-between" mb="xs">
                  <Group gap="xs">
                    {renderTypeBadge(q.question_type)}
                    <Badge variant="filled" color={renderBloomColor(q.bloom_level)}>
                      {q.bloom_level}
                    </Badge>
                  </Group>
                  <Group gap="xs">
                    {q.status === 'final' ? (
                      <Badge color="green" variant="light" leftSection={<IconCheck size={12} />}>
                        Lolos Validasi
                      </Badge>
                    ) : (
                      <Badge color="orange" variant="light" leftSection={<IconAlertTriangle size={12} />}>
                        Perlu Tinjauan
                      </Badge>
                    )}
                    <Badge variant="outline" color="gray" size="xs">
                      Revisi: {q.refinement_count}x
                    </Badge>
                  </Group>
                </Group>

                <Text fw={600} size="sm" lineClamp={3} mb="xs">
                  {idx + 1}. {q.question_text}
                </Text>

                {q.answer_key && (
                  <Text size="xs" c="dimmed" lineClamp={2}>
                    <strong>Kunci/Rubrik Jawaban:</strong> {q.answer_key}
                  </Text>
                )}
              </Card>
            ))}
          </Stack>

          {/* Audit Inspector Column */}
          <Stack gap="md">
            <Title order={4}>Detail & Log Audit Validasi</Title>
            {loadingDetail ? (
              <Paper p="xl" radius="md" withBorder style={{ textAlign: 'center' }}>
                <Loader size="sm" mb="xs" />
                <Text size="sm" c="dimmed">Memuat log validasi...</Text>
              </Paper>
            ) : selectedQuestion ? (
              <Paper p="md" radius="md" withBorder>
                <Group justify="space-between" mb="xs">
                  <Group gap="xs">
                    {renderTypeBadge(selectedQuestion.question_type)}
                    <Badge variant="filled" color={renderBloomColor(selectedQuestion.bloom_level)}>
                      {selectedQuestion.bloom_level}
                    </Badge>
                  </Group>
                  <Badge color={selectedQuestion.status === 'final' ? 'green' : 'orange'}>
                    Status: {selectedQuestion.status.toUpperCase()}
                  </Badge>
                </Group>

                <Title order={4} mb="sm" style={{ lineHeight: '1.4' }}>
                  {selectedQuestion.question_text}
                </Title>

                {renderOptionsList(selectedQuestion.options)}

                {/* Jawaban Benar */}
                <Paper p="sm" radius="xs" withBorder mb="xs" style={{ backgroundColor: 'rgba(34, 139, 230, 0.05)', borderColor: 'var(--mantine-color-blue-4)' }}>
                  <Text size="xs" fw={700} c="blue" mb={4}>
                    Jawaban yang Benar:
                  </Text>
                  <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                    {selectedQuestion.answer_key}
                  </Text>
                </Paper>

                {/* Penjelasan */}
                {selectedQuestion.explanation && (
                  <Paper p="sm" radius="xs" withBorder mb="xs" style={{ backgroundColor: 'rgba(18, 184, 134, 0.05)', borderColor: 'var(--mantine-color-teal-4)' }}>
                    <Text size="xs" fw={700} c="teal" mb={4}>
                      Penjelasan & Konsep Acuan:
                    </Text>
                    <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                      {selectedQuestion.explanation}
                    </Text>
                  </Paper>
                )}

                {/* Referensi Materi */}
                {selectedQuestion.source_reference && (
                  <Paper p="xs" px="sm" radius="xs" withBorder mb="xs" style={{ backgroundColor: 'rgba(134, 142, 150, 0.05)', borderColor: 'var(--mantine-color-gray-4)' }}>
                    <Text size="xs" fw={700} c="dimmed" mb={2}>
                      Referensi Lokasi Materi Soal:
                    </Text>
                    <Badge color="gray" variant="light" size="sm">
                      {selectedQuestion.source_reference}
                    </Badge>
                  </Paper>
                )}

                {/* Konteks Chunk Materi yang Digunakan */}
                <Title order={5} mt="md" mb="xs">
                  Konteks Chunk Materi yang Digunakan ({selectedQuestion.used_chunks?.length || 0} Chunk)
                </Title>

                {selectedQuestion.used_chunks && selectedQuestion.used_chunks.length > 0 ? (
                  <Accordion variant="separated" radius="md" mb="md">
                    {selectedQuestion.used_chunks.map((chunk, cIdx) => (
                      <Accordion.Item key={chunk.id || cIdx} value={chunk.id || `chunk-${cIdx}`}>
                        <Accordion.Control icon={<IconFileText size={18} color="var(--mantine-color-teal-6)" />}>
                          <Group justify="space-between" wrap="nowrap">
                            <Group gap="xs">
                              <Badge size="xs" color={chunk.category === 'KONSEP' ? 'blue' : chunk.category === 'NARASI' ? 'cyan' : 'gray'}>
                                {chunk.category || 'Materi'}
                              </Badge>
                              <Text size="xs" fw={600} lineClamp={1}>
                                {chunk.chapter ? `Bab ${chunk.chapter}` : ''} {chunk.section_heading ? `— ${chunk.section_heading}` : ''}
                              </Text>
                            </Group>
                            <Text size="xs" c="dimmed">
                              ID: {chunk.id.slice(0, 8)}...
                            </Text>
                          </Group>
                        </Accordion.Control>
                        <Accordion.Panel>
                          <Paper p="xs" radius="xs" withBorder style={{ backgroundColor: 'var(--mantine-color-body)' }}>
                            <Text size="xs" style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', lineHeight: '1.5' }}>
                              {chunk.text}
                            </Text>
                          </Paper>
                        </Accordion.Panel>
                      </Accordion.Item>
                    ))}
                  </Accordion>
                ) : (
                  <Text size="xs" c="dimmed" mb="md">Tidak ada data chunk tersimpan untuk soal ini.</Text>
                )}

                <Title order={5} mb="xs">
                  Riwayat Percobaan Self-Refinement ({selectedQuestion.validation_logs?.length || 0} Log)
                </Title>

                {selectedQuestion.validation_logs && selectedQuestion.validation_logs.length > 0 ? (
                  <Accordion variant="separated" radius="md">
                    {selectedQuestion.validation_logs.map((log) => (
                      <Accordion.Item key={log.id} value={log.id}>
                        <Accordion.Control icon={<IconScale size={18} color="var(--mantine-color-blue-6)" />}>
                          <Group justify="space-between" wrap="nowrap">
                            <Text size="xs" fw={600}>
                              Percobaan #{log.attempt_number} — {log.layer === 'grounding' ? 'Lapis 1 (Grounding)' : 'Lapis 2 (LLM Judge)'}
                            </Text>
                            <Badge size="xs" color={log.score_or_verdict.includes('pass') ? 'green' : 'red'}>
                              {log.score_or_verdict}
                            </Badge>
                          </Group>
                        </Accordion.Control>
                        <Accordion.Panel>
                          <Text size="xs" c="dimmed" style={{ whiteSpace: 'pre-wrap' }}>
                            <strong>Feedback:</strong> {log.feedback || 'Tidak ada catatan.'}
                          </Text>
                        </Accordion.Panel>
                      </Accordion.Item>
                    ))}
                  </Accordion>
                ) : (
                  <Text size="xs" c="dimmed">Belum ada catatan log validasi.</Text>
                )}
              </Paper>
            ) : (
              <Alert color="blue" icon={<IconShieldCheck size={18} />}>
                Klik salah satu soal di sebelah kiri untuk melihat detail pertanyaan, kunci/rubrik jawaban, konteks chunk materi yang digunakan, serta riwayat log validasi 2-layer.
              </Alert>
            )}
          </Stack>
        </SimpleGrid>
      )}
    </Stack>
  );
}
