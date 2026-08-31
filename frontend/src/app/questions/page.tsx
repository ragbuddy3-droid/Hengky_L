'use client';

import { useState, useEffect } from 'react';
import {
  Title,
  Text,
  Stack,
  Paper,
  Group,
  Badge,
  Card,
  Accordion,
  Loader,
  Alert,
  Button,
  SimpleGrid,
  Tabs,
  Table,
  Code,
  Divider,
  ThemeIcon,
  Box,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconQuestionMark,
  IconCheck,
  IconAlertTriangle,
  IconShieldCheck,
  IconRefresh,
  IconScale,
  IconFileText,
  IconBrain,
  IconLayersLinked,
  IconListCheck,
  IconSparkles,
  IconCode,
  IconClock,
  IconQuote,
  IconArrowRight,
} from '@tabler/icons-react';
import { api } from '@/lib/api';
import { Question, PromptTraceItem, ValidationLog } from '@/types/question';

export default function QuestionsPage() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedQuestion, setSelectedQuestion] = useState<Question | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [activeTab, setActiveTab] = useState<string | null>('preview');

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
      setActiveTab('preview');
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
    if (!bloom) return 'gray';
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

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="center">
        <div>
          <Title order={2}>Bank & Multi-Stage Prompt Inspector</Title>
          <Text c="dimmed" size="sm">
            Tinjau seluruh soal esai & isian singkat (C1–C4 SD), rubrik penskoran bertingkat, serta inspeksi output dari setiap tahapan prompt (Stage 1 s.d. Stage 4 & Validasi 2-Layer).
          </Text>
        </div>
        <Button variant="light" leftSection={<IconRefresh size={16} />} onClick={fetchQuestions} loading={loading}>
          Refresh Soal
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
        <SimpleGrid cols={{ base: 1, lg: 12 }} spacing="lg">
          {/* ── Left Column: Question List (4 cols) ── */}
          <Box style={{ gridColumn: 'span 4' }}>
            <Stack gap="md">
              <Group justify="space-between">
                <Title order={4}>Daftar Soal ({questions.length})</Title>
                <Badge variant="light" color="gray">{questions.filter(q => q.status === 'final').length} Lolos Validasi</Badge>
              </Group>

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
                    transition: 'border-color 0.2s ease',
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
                        <Badge color="green" variant="light" size="xs" leftSection={<IconCheck size={10} />}>
                          Lolos
                        </Badge>
                      ) : (
                        <Badge color="orange" variant="light" size="xs" leftSection={<IconAlertTriangle size={10} />}>
                          Tinjau
                        </Badge>
                      )}
                      <Badge variant="outline" color="gray" size="xs">
                        {q.refinement_count}x Rev
                      </Badge>
                    </Group>
                  </Group>

                  <Text fw={600} size="sm" lineClamp={2} mb="xs">
                    {idx + 1}. {q.question_text}
                  </Text>

                  {q.knowledge_point && (
                    <Text size="xs" c="blue" fw={500} lineClamp={1} mb={4}>
                      📍 {q.knowledge_point}
                    </Text>
                  )}

                  {q.answer_key && (
                    <Text size="xs" c="dimmed" lineClamp={2}>
                      <strong>Jawaban:</strong> {q.answer_key}
                    </Text>
                  )}
                </Card>
              ))}
            </Stack>
          </Box>

          {/* ── Right Column: Multi-Stage Inspector (8 cols) ── */}
          <Box style={{ gridColumn: 'span 8' }}>
            <Stack gap="md">
              <Title order={4}>Multi-Stage Prompt Inspector & Audit Validasi</Title>
              {loadingDetail ? (
                <Paper p="xl" radius="md" withBorder style={{ textAlign: 'center' }}>
                  <Loader size="sm" mb="xs" />
                  <Text size="sm" c="dimmed">Memuat trace eksekusi prompt & rubrik soal...</Text>
                </Paper>
              ) : selectedQuestion ? (
                <Paper p="md" radius="md" withBorder>
                  {/* Question Header Card */}
                  <Group justify="space-between" mb="xs">
                    <Group gap="xs">
                      {renderTypeBadge(selectedQuestion.question_type)}
                      <Badge variant="filled" color={renderBloomColor(selectedQuestion.bloom_level)} size="md">
                        {selectedQuestion.bloom_level}
                      </Badge>
                      {selectedQuestion.knowledge_point && (
                        <Badge variant="light" color="teal" size="sm">
                          {selectedQuestion.knowledge_point}
                        </Badge>
                      )}
                    </Group>
                    <Badge color={selectedQuestion.status === 'final' ? 'green' : 'orange'} variant="filled">
                      {selectedQuestion.status === 'final' ? 'VALID / LOLOS' : 'PERLU TINJAUAN'}
                    </Badge>
                  </Group>

                  <Title order={4} mb="md" style={{ lineHeight: '1.4' }}>
                    {selectedQuestion.question_text}
                  </Title>

                  {/* Tabs: Preview vs Multi-Stage Pipeline Traces */}
                  <Tabs value={activeTab} onChange={setActiveTab} variant="outline" radius="md">
                    <Tabs.List mb="md">
                      <Tabs.Tab value="preview" leftSection={<IconListCheck size={16} />}>
                        Paket Soal & Rubrik
                      </Tabs.Tab>
                      <Tabs.Tab value="stages" leftSection={<IconLayersLinked size={16} />}>
                        4 Tahap Generasi
                      </Tabs.Tab>
                      <Tabs.Tab value="validation" leftSection={<IconScale size={16} />}>
                        Validasi 2-Layer ({selectedQuestion.validation_logs?.length || 0})
                      </Tabs.Tab>
                      <Tabs.Tab value="traces" leftSection={<IconCode size={16} />}>
                        Raw Prompt Traces ({selectedQuestion.prompt_traces?.length || 0})
                      </Tabs.Tab>
                      <Tabs.Tab value="chunks" leftSection={<IconFileText size={16} />}>
                        Konteks Buku ({selectedQuestion.used_chunks?.length || 0})
                      </Tabs.Tab>
                    </Tabs.List>

                    {/* ── TAB 1: Preview Soal & Rubrik ── */}
                    <Tabs.Panel value="preview">
                      <Stack gap="md">
                        {/* Jawaban Ideal */}
                        <Paper p="sm" radius="xs" withBorder style={{ backgroundColor: 'rgba(34, 139, 230, 0.05)', borderColor: 'var(--mantine-color-blue-4)' }}>
                          <Text size="xs" fw={700} c="blue" mb={4}>
                            Jawaban Ideal (Expected Answer):
                          </Text>
                          <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                            {selectedQuestion.answer_key}
                          </Text>
                        </Paper>

                        {/* Grounding Evidence Quote */}
                        {selectedQuestion.grounding_evidence && (
                          <Paper p="sm" radius="xs" withBorder style={{ backgroundColor: 'rgba(250, 176, 5, 0.05)', borderColor: 'var(--mantine-color-yellow-4)' }}>
                            <Group gap="xs" mb={4}>
                              <IconQuote size={16} color="var(--mantine-color-yellow-7)" />
                              <Text size="xs" fw={700} c="yellow.8">
                                Kutipan Bukti Materi Buku (Grounding Evidence):
                              </Text>
                            </Group>
                            <Text size="xs" fs="italic" style={{ whiteSpace: 'pre-wrap' }}>
                              "{selectedQuestion.grounding_evidence}"
                            </Text>
                          </Paper>
                        )}

                        {/* Rubrik Penilaian Bertingkat (Score 0, 1, 2+) */}
                        <div>
                          <Text size="xs" fw={700} c="dimmed" mb="xs">
                            RUBRIK PENILAIAN BERTINGKAT:
                          </Text>
                          {selectedQuestion.rubric && selectedQuestion.rubric.length > 0 ? (
                            <Table withTableBorder withColumnBorders highlightOnHover verticalSpacing="xs">
                              <Table.Thead style={{ backgroundColor: 'var(--mantine-color-body)' }}>
                                <Table.Tr>
                                  <Table.Th style={{ width: '90px' }}>Skor</Table.Th>
                                  <Table.Th>Kriteria Pemenuhan Jawaban</Table.Th>
                                </Table.Tr>
                              </Table.Thead>
                              <Table.Tbody>
                                {selectedQuestion.rubric.map((r, rIdx) => (
                                  <Table.Tr key={rIdx}>
                                    <Table.Td>
                                      <Badge color={r.score === 0 ? 'gray' : r.score === 1 ? 'blue' : 'green'} variant="filled" size="sm">
                                        Skor {r.score}
                                      </Badge>
                                    </Table.Td>
                                    <Table.Td>
                                      <Text size="xs">{r.criteria}</Text>
                                    </Table.Td>
                                  </Table.Tr>
                                ))}
                              </Table.Tbody>
                            </Table>
                          ) : (
                            <Text size="xs" c="dimmed">Belum ada rubrik terstruktur.</Text>
                          )}
                        </div>

                        {/* Elemen Kunci Jawaban */}
                        {selectedQuestion.answer_elements && selectedQuestion.answer_elements.length > 0 && (
                          <div>
                            <Text size="xs" fw={700} c="dimmed" mb="xs">
                              ELEMEN KUNCI JAWABAN (ANSWER ELEMENTS):
                            </Text>
                            <Group gap="xs">
                              {selectedQuestion.answer_elements.map((elem, eIdx) => (
                                <Badge key={eIdx} variant="outline" color="teal" size="sm">
                                  {elem.element} (Bobot: {elem.weight})
                                </Badge>
                              ))}
                            </Group>
                          </div>
                        )}

                        {/* Penjelasan & Lokasi Referensi */}
                        <Group grow align="stretch">
                          {selectedQuestion.explanation && (
                            <Paper p="xs" px="sm" radius="xs" withBorder style={{ backgroundColor: 'var(--mantine-color-body)' }}>
                              <Text size="xs" fw={700} c="teal" mb={2}>Penjelasan:</Text>
                              <Text size="xs">{selectedQuestion.explanation}</Text>
                            </Paper>
                          )}
                          {selectedQuestion.source_reference && (
                            <Paper p="xs" px="sm" radius="xs" withBorder style={{ backgroundColor: 'var(--mantine-color-body)' }}>
                              <Text size="xs" fw={700} c="dimmed" mb={2}>Referensi Buku:</Text>
                              <Text size="xs">{selectedQuestion.source_reference}</Text>
                            </Paper>
                          )}
                        </Group>
                      </Stack>
                    </Tabs.Panel>

                    {/* ── TAB 2: Detail 4 Tahap Generasi ── */}
                    <Tabs.Panel value="stages">
                      <Stack gap="md">
                        {/* Stage 1 Breakdown */}
                        <Paper p="sm" radius="md" withBorder>
                          <Group justify="space-between" mb="xs">
                            <Group gap="xs">
                              <ThemeIcon color="indigo" variant="light" size="md">
                                <IconBrain size={18} />
                              </ThemeIcon>
                              <Text size="sm" fw={700}>Stage 1: Context Understanding</Text>
                            </Group>
                            <Badge color="indigo" variant="light" size="xs">Analisis Materi</Badge>
                          </Group>
                          {(() => {
                            const trace = selectedQuestion.prompt_traces?.find(t => t.stage_name.includes('Stage 1'));
                            const parsed = trace?.parsed_output;
                            if (!parsed) return <Text size="xs" c="dimmed">Data Stage 1 tidak tersedia.</Text>;
                            return (
                              <Stack gap="xs">
                                <Text size="xs"><strong>Topik:</strong> {parsed.topic || '-'}</Text>
                                {parsed.subtopics?.length > 0 && (
                                  <Text size="xs"><strong>Subtopik:</strong> {parsed.subtopics.join(', ')}</Text>
                                )}
                                {parsed.key_concepts?.length > 0 && (
                                  <div>
                                    <Text size="xs" fw={600} mb={4}>Konsep Kunci:</Text>
                                    <Group gap={4}>
                                      {parsed.key_concepts.map((kc: string, i: number) => (
                                        <Badge key={i} size="xs" variant="outline" color="blue">{kc}</Badge>
                                      ))}
                                    </Group>
                                  </div>
                                )}
                                {parsed.testable_content?.length > 0 && (
                                  <div>
                                    <Text size="xs" fw={600} mb={4}>Testable Content (Kutipan Kalimat):</Text>
                                    <Stack gap={4}>
                                      {parsed.testable_content.map((tc: any, i: number) => (
                                        <Paper key={i} p={6} withBorder radius="xs" style={{ backgroundColor: 'var(--mantine-color-body)' }}>
                                          <Text size="xs" fw={600}>• {tc.point}</Text>
                                          <Text size="xs" c="dimmed" fs="italic">"{tc.source_quote}"</Text>
                                        </Paper>
                                      ))}
                                    </Stack>
                                  </div>
                                )}
                              </Stack>
                            );
                          })()}
                        </Paper>

                        {/* Stage 2 Breakdown */}
                        <Paper p="sm" radius="md" withBorder>
                          <Group justify="space-between" mb="xs">
                            <Group gap="xs">
                              <ThemeIcon color="cyan" variant="light" size="md">
                                <IconSparkles size={18} />
                              </ThemeIcon>
                              <Text size="sm" fw={700}>Stage 2: Cognitive Bloom Planning</Text>
                            </Group>
                            <Badge color="cyan" variant="light" size="xs">Perencanaan Kognitif</Badge>
                          </Group>
                          {(() => {
                            const trace = selectedQuestion.prompt_traces?.find(t => t.stage_name.includes('Stage 2') || t.stage_name.includes('Refinement Prompt B'));
                            const parsed = trace?.parsed_output;
                            if (!parsed) return <Text size="xs" c="dimmed">Data Stage 2 tidak tersedia.</Text>;
                            return (
                              <Stack gap="xs">
                                <Group gap="xs">
                                  <Badge color="blue" size="xs">{parsed.cognitive_level || selectedQuestion.bloom_level}</Badge>
                                  <Badge color="violet" size="xs">{parsed.recommended_question_format || 'esai'}</Badge>
                                </Group>
                                <Text size="xs"><strong>Operasi Kognitif:</strong> {parsed.cognitive_operation}</Text>
                                <Text size="xs"><strong>Tugas Siswa (Task):</strong> {parsed.student_task}</Text>
                                <Text size="xs"><strong>Penalaran yang Dibutuhkan:</strong> {parsed.reasoning_required}</Text>
                                {parsed.prohibited_question_pattern?.length > 0 && (
                                  <div>
                                    <Text size="xs" fw={600} c="red" mb={2}>Pola Pertanyaan Terlarang:</Text>
                                    <Group gap={4}>
                                      {parsed.prohibited_question_pattern.map((p: string, i: number) => (
                                        <Badge key={i} size="xs" color="red" variant="light">{p}</Badge>
                                      ))}
                                    </Group>
                                  </div>
                                )}
                              </Stack>
                            );
                          })()}
                        </Paper>

                        {/* Stage 3 Breakdown */}
                        <Paper p="sm" radius="md" withBorder>
                          <Group justify="space-between" mb="xs">
                            <Group gap="xs">
                              <ThemeIcon color="teal" variant="light" size="md">
                                <IconLayersLinked size={18} />
                              </ThemeIcon>
                              <Text size="sm" fw={700}>Stage 3: Question Blueprint</Text>
                            </Group>
                            <Badge color="teal" variant="light" size="xs">Rancangan Soal</Badge>
                          </Group>
                          {(() => {
                            const trace = selectedQuestion.prompt_traces?.find(t => t.stage_name.includes('Stage 3'));
                            const parsed = trace?.parsed_output;
                            if (!parsed) return <Text size="xs" c="dimmed">Data Stage 3 tidak tersedia.</Text>;
                            return (
                              <Stack gap="xs">
                                <Text size="xs"><strong>Pokok Materi:</strong> {parsed.knowledge_point}</Text>
                                <Text size="xs"><strong>Indikator/Intent:</strong> {parsed.question_intent}</Text>
                                {parsed.grounding_evidence && (
                                  <Text size="xs" fs="italic" c="dimmed">
                                    <strong>Grounding Evidence:</strong> "{parsed.grounding_evidence}"
                                  </Text>
                                )}
                                {parsed.expected_answer_elements?.length > 0 && (
                                  <div>
                                    <Text size="xs" fw={600} mb={2}>Ekspektasi Elemen Jawaban:</Text>
                                    {parsed.expected_answer_elements.map((el: string, i: number) => (
                                      <Text key={i} size="xs" c="teal">• {el}</Text>
                                    ))}
                                  </div>
                                )}
                              </Stack>
                            );
                          })()}
                        </Paper>

                        {/* Stage 4 Breakdown */}
                        <Paper p="sm" radius="md" withBorder>
                          <Group justify="space-between" mb="xs">
                            <Group gap="xs">
                              <ThemeIcon color="grape" variant="light" size="md">
                                <IconListCheck size={18} />
                              </ThemeIcon>
                              <Text size="sm" fw={700}>Stage 4: Question Generation Package</Text>
                            </Group>
                            <Badge color="grape" variant="light" size="xs">Paket Soal Final</Badge>
                          </Group>
                          <Text size="xs">Soal, kunci jawaban ideal, dan rubrik penskoran terintegrasi dihasilkan secara utuh mengikuti blueprint.</Text>
                        </Paper>
                      </Stack>
                    </Tabs.Panel>

                    {/* ── TAB 3: Validasi 2-Layer ── */}
                    <Tabs.Panel value="validation">
                      <Stack gap="md">
                        {selectedQuestion.validation_logs && selectedQuestion.validation_logs.length > 0 ? (
                          <Accordion variant="separated" radius="md">
                            {selectedQuestion.validation_logs.map((log) => {
                              const aspects = typeof log.aspect_evaluations === 'string'
                                ? (() => { try { return json.parse(log.aspect_evaluations); } catch { return null; } })()
                                : log.aspect_evaluations;

                              return (
                                <Accordion.Item key={log.id} value={log.id}>
                                  <Accordion.Control icon={<IconScale size={18} color="var(--mantine-color-blue-6)" />}>
                                    <Group justify="space-between" wrap="nowrap">
                                      <Text size="xs" fw={600}>
                                        Percobaan #{log.attempt_number} — {log.layer === 'grounding' ? 'Lapis 1 (Fast-Reject Grounding)' : log.layer === 'judge' ? 'Lapis 2 (LLM-as-Judge 5 Aspek SD)' : 'Pre-Check Filter'}
                                      </Text>
                                      <Badge size="xs" color={log.score_or_verdict.includes('pass') ? 'green' : 'red'}>
                                        {log.score_or_verdict}
                                      </Badge>
                                    </Group>
                                  </Accordion.Control>
                                  <Accordion.Panel>
                                    <Stack gap="xs">
                                      <Text size="xs">
                                        <strong>Feedback:</strong> {log.feedback || 'Tidak ada catatan khusus.'}
                                      </Text>
                                      {aspects && typeof aspects === 'object' && (
                                        <Paper p="xs" withBorder radius="xs" style={{ backgroundColor: 'var(--mantine-color-body)' }}>
                                          <Text size="xs" fw={700} c="dimmed" mb={4}>Rincian Evaluasi Aspek Juri:</Text>
                                          <SimpleGrid cols={2} spacing="xs">
                                            {Object.entries(aspects).map(([k, v]: [string, any]) => {
                                              if (typeof v === 'object' && v !== null && 'status' in v) {
                                                return (
                                                  <Paper key={k} p={4} px={8} withBorder radius="xs">
                                                    <Group justify="space-between">
                                                      <Text size="xs" fw={600}>{k}:</Text>
                                                      <Badge size="xs" color={v.status === 'pass' ? 'green' : 'red'}>{v.status}</Badge>
                                                    </Group>
                                                    {v.feedback && <Text size="xs" c="dimmed" lineClamp={2}>{v.feedback}</Text>}
                                                  </Paper>
                                                );
                                              }
                                              return null;
                                            })}
                                          </SimpleGrid>
                                        </Paper>
                                      )}
                                    </Stack>
                                  </Accordion.Panel>
                                </Accordion.Item>
                              );
                            })}
                          </Accordion>
                        ) : (
                          <Text size="xs" c="dimmed">Belum ada catatan log validasi.</Text>
                        )}
                      </Stack>
                    </Tabs.Panel>

                    {/* ── TAB 4: Raw Prompt Traces Inspector ── */}
                    <Tabs.Panel value="traces">
                      <Stack gap="md">
                        <Text size="xs" c="dimmed">
                          Inspeksi transparan terhadap teks prompt lengkap yang dikirim ke LLM, durasi latensi (ms), respons teks mentah, dan output JSON yang diparse pada setiap tahapan:
                        </Text>
                        {selectedQuestion.prompt_traces && selectedQuestion.prompt_traces.length > 0 ? (
                          <Accordion variant="separated" radius="md">
                            {selectedQuestion.prompt_traces.map((trace, tIdx) => (
                              <Accordion.Item key={tIdx} value={`trace-${tIdx}`}>
                                <Accordion.Control icon={<IconCode size={18} color="var(--mantine-color-teal-6)" />}>
                                  <Group justify="space-between" wrap="nowrap">
                                    <Group gap="xs">
                                      <Badge size="xs" color="indigo">Step {trace.step_number}</Badge>
                                      <Text size="xs" fw={600}>{trace.stage_name}</Text>
                                    </Group>
                                    <Group gap="xs">
                                      <Badge size="xs" variant="outline" color="gray" leftSection={<IconClock size={10} />}>
                                        {trace.latency_ms} ms
                                      </Badge>
                                      <Badge size="xs" color={trace.status === 'success' ? 'green' : 'orange'}>
                                        {trace.status}
                                      </Badge>
                                    </Group>
                                  </Group>
                                </Accordion.Control>
                                <Accordion.Panel>
                                  <Stack gap="xs">
                                    <div>
                                      <Text size="xs" fw={700} c="blue" mb={2}>Prompt Sent to LLM:</Text>
                                      <Code block style={{ maxHeight: '180px', overflowY: 'auto', fontSize: '11px' }}>
                                        {trace.prompt_sent}
                                      </Code>
                                    </div>
                                    <Divider my="xs" />
                                    <div>
                                      <Text size="xs" fw={700} c="teal" mb={2}>Parsed Structured JSON:</Text>
                                      <Code block style={{ maxHeight: '200px', overflowY: 'auto', fontSize: '11px' }}>
                                        {JSON.stringify(trace.parsed_output, null, 2)}
                                      </Code>
                                    </div>
                                    <Divider my="xs" />
                                    <div>
                                      <Text size="xs" fw={700} c="dimmed" mb={2}>Raw Response Text:</Text>
                                      <Code block style={{ maxHeight: '120px', overflowY: 'auto', fontSize: '11px' }}>
                                        {trace.raw_response}
                                      </Code>
                                    </div>
                                  </Stack>
                                </Accordion.Panel>
                              </Accordion.Item>
                            ))}
                          </Accordion>
                        ) : (
                          <Alert color="blue" icon={<IconShieldCheck size={16} />}>
                            Data jejak prompt trace belum terekam untuk soal ini. Soal yang baru dibuat akan menyimpan trace lengkap di tab ini.
                          </Alert>
                        )}
                      </Stack>
                    </Tabs.Panel>

                    {/* ── TAB 5: Used Chunks ── */}
                    <Tabs.Panel value="chunks">
                      <Stack gap="md">
                        {selectedQuestion.used_chunks && selectedQuestion.used_chunks.length > 0 ? (
                          <Accordion variant="separated" radius="md">
                            {selectedQuestion.used_chunks.map((chunk, cIdx) => (
                              <Accordion.Item key={chunk.id || cIdx} value={chunk.id || `chunk-${cIdx}`}>
                                <Accordion.Control icon={<IconFileText size={18} color="var(--mantine-color-teal-6)" />}>
                                  <Group justify="space-between" wrap="nowrap">
                                    <Group gap="xs">
                                      <Badge size="xs" variant="outline" color="gray">
                                        Chunk #{chunk.chunk_index !== undefined && chunk.chunk_index !== null ? chunk.chunk_index + 1 : cIdx + 1}
                                      </Badge>
                                      {chunk.page_number && (
                                        <Badge size="xs" variant="filled" color="indigo">
                                          Hal. {chunk.page_number}
                                        </Badge>
                                      )}
                                      <Badge size="xs" color={['materi_pokok', 'konsep'].includes((chunk.category || '').toLowerCase()) ? 'blue' : 'cyan'}>
                                        {chunk.section_type || chunk.category || 'Materi'}
                                      </Badge>
                                      <Text size="xs" fw={600} lineClamp={1}>
                                        {chunk.chapter ? `${chunk.chapter}` : ''} {chunk.section_heading ? `— ${chunk.section_heading}` : ''}
                                      </Text>
                                    </Group>
                                    <Text size="xs" c="dimmed">
                                      ID: {chunk.id?.slice(0, 8)}...
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
                          <Text size="xs" c="dimmed">Tidak ada data chunk tersimpan untuk soal ini.</Text>
                        )}
                      </Stack>
                    </Tabs.Panel>
                  </Tabs>
                </Paper>
              ) : (
                <Alert color="blue" icon={<IconShieldCheck size={18} />}>
                  Klik salah satu soal di sebelah kiri untuk membuka **Multi-Stage Prompt Inspector**, melihat rincian 4 tahap generasi, rubrik penskoran bertingkat, log validasi 2-layer, dan teks raw prompt.
                </Alert>
              )}
            </Stack>
          </Box>
        </SimpleGrid>
      )}
    </Stack>
  );
}
