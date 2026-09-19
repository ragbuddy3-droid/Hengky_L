'use client';

import { useState, useEffect } from 'react';
import { Title, Text, Table, Badge, Button, Group, Stack, Select, Paper, ActionIcon, Loader, Alert, Drawer, Card, ScrollArea, TextInput } from '@mantine/core';
import { Dropzone, PDF_MIME_TYPE } from '@mantine/dropzone';
import { notifications } from '@mantine/notifications';
import { IconUpload, IconFile, IconX, IconTrash, IconCheck, IconAlertCircle, IconRefresh, IconEye, IconSearch, IconFileText } from '@tabler/icons-react';
import { api } from '@/lib/api';
import { Document, DocumentChunk } from '@/types/document';

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [selectedSubject, setSelectedSubject] = useState<string>('IPAS');

  // Chunk Drawer State
  const [selectedDocForChunks, setSelectedDocForChunks] = useState<Document | null>(null);
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [loadingChunks, setLoadingChunks] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      const docs = await api.listDocuments();
      setDocuments(docs);
    } catch (err: any) {
      notifications.show({
        title: 'Gagal Memuat Dokumen',
        message: err.message || 'Tidak dapat menghubungkan ke backend.',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  // Poll processing status
  useEffect(() => {
    const hasProcessing = documents.some((doc) => doc.status === 'processing' || doc.status === 'pending');
    if (!hasProcessing) return;

    const interval = setInterval(async () => {
      const updatedDocs = await api.listDocuments();
      setDocuments(updatedDocs);
    }, 3000);

    return () => clearInterval(interval);
  }, [documents]);

  const handleDrop = async (files: File[]) => {
    if (files.length === 0) return;
    const file = files[0];

    try {
      setUploading(true);
      await api.uploadDocument(file, selectedSubject, 'fixed');
      notifications.show({
        title: 'Upload Berhasil',
        message: `${file.name} telah diunggah dan sedang diproses dengan strategi Fixed Chunking (1000 Karakter).`,
        color: 'green',
        icon: <IconCheck size={18} />,
      });
      fetchDocuments();
    } catch (err: any) {
      notifications.show({
        title: 'Upload Gagal',
        message: err.message || 'Gagal mengunggah file.',
        color: 'red',
        icon: <IconAlertCircle size={18} />,
      });
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (id: string, filename: string) => {
    if (!confirm(`Apakah Anda yakin ingin menghapus dokumen '${filename}'?`)) return;

    try {
      await api.deleteDocument(id);
      notifications.show({
        title: 'Dokumen Dihapus',
        message: `File ${filename} berhasil dihapus dari sistem.`,
        color: 'blue',
      });
      setDocuments(documents.filter((d) => d.id !== id));
    } catch (err: any) {
      notifications.show({
        title: 'Gagal Menghapus',
        message: err.message || 'Terjadi kesalahan saat menghapus.',
        color: 'red',
      });
    }
  };

  const handleViewChunks = async (doc: Document) => {
    setSelectedDocForChunks(doc);
    setDrawerOpen(true);
    setLoadingChunks(true);
    setSearchQuery('');
    try {
      const data = await api.listDocumentChunks(doc.id);
      setChunks(data);
    } catch (err: any) {
      notifications.show({
        title: 'Gagal Memuat Chunk',
        message: err.message || 'Gagal mengambil chunk untuk dokumen ini.',
        color: 'red',
      });
      setChunks([]);
    } finally {
      setLoadingChunks(false);
    }
  };

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case 'ready':
        return <Badge color="green" variant="light">Ready</Badge>;
      case 'processing':
        return <Badge color="blue" variant="light" leftSection={<Loader size={10} color="blue" />}>Processing</Badge>;
      case 'pending':
        return <Badge color="yellow" variant="light">Pending</Badge>;
      case 'failed':
        return <Badge color="red" variant="light">Failed</Badge>;
      default:
        return <Badge color="gray" variant="light">{status}</Badge>;
    }
  };

  const renderCategoryBadge = (category: string) => {
    const catLower = (category || '').toLowerCase();
    switch (catLower) {
      case 'materi_pokok':
      case 'konsep':
        return <Badge color="blue" variant="filled">Materi Pokok</Badge>;
      case 'uraian_materi':
      case 'narasi':
        return <Badge color="teal" variant="filled">Uraian Materi</Badge>;
      case 'studi_kasus':
        return <Badge color="cyan" variant="filled">Studi Kasus</Badge>;
      case 'aktivitas_diskusi':
      case 'instruksi':
        return <Badge color="orange" variant="filled">Aktivitas / Diskusi</Badge>;
      case 'rangkuman':
      case 'evaluasi':
        return <Badge color="grape" variant="filled">Rangkuman</Badge>;
      default:
        return <Badge color="gray" variant="filled">{category || 'Materi'}</Badge>;
    }
  };

  const filteredChunks = chunks.filter((c) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      c.text.toLowerCase().includes(q) ||
      (c.section_heading && c.section_heading.toLowerCase().includes(q)) ||
      (c.chapter && c.chapter.toLowerCase().includes(q)) ||
      c.category.toLowerCase().includes(q)
    );
  });

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="center">
        <div>
          <Title order={2}>Manajemen Dokumen Buku PDF</Title>
          <Text c="dimmed" size="sm">
            Unggah dokumen PDF buku pelajaran yang akan diekstrak dan diindeks secara Fixed Chunking untuk Automatic Question Generation.
          </Text>
        </div>
        <Button variant="light" leftSection={<IconRefresh size={16} />} onClick={fetchDocuments} loading={loading}>
          Refresh
        </Button>
      </Group>

      <Paper p="md" radius="md" withBorder>
        <Group align="flex-end" mb="md" gap="md">
          <Select
            label="Mata Pelajaran"
            placeholder="Pilih Subjek"
            value={selectedSubject}
            onChange={(val) => setSelectedSubject(val || 'IPAS')}
            data={['IPAS', 'PJOK', 'PKN', 'Matematika', 'Umum']}
            style={{ width: '200px' }}
          />
          <Paper withBorder p="xs" px="md" radius="sm" style={{ backgroundColor: 'var(--mantine-color-gray-0)' }}>
            <Text size="xs" c="dimmed">Metode Chunking</Text>
            <Text size="sm" fw={600} c="blue">Fixed Chunking (1000 Karakter, Overlap 150)</Text>
          </Paper>
          <Text size="xs" c="dimmed" pb={8}>
            Pemotongan materi fixed-size dengan pemetaan bab, topik, dan halaman.
          </Text>
        </Group>

        <Dropzone
          onDrop={handleDrop}
          accept={PDF_MIME_TYPE}
          maxFiles={1}
          loading={uploading}
          radius="md"
        >
          <Group justify="center" gap="xl" style={{ minHeight: 120, pointerEvents: 'none' }}>
            <Dropzone.Accept>
              <IconUpload size={50} color="var(--mantine-color-blue-6)" />
            </Dropzone.Accept>
            <Dropzone.Reject>
              <IconX size={50} color="var(--mantine-color-red-6)" />
            </Dropzone.Reject>
            <Dropzone.Idle>
              <IconFile size={50} color="var(--mantine-color-dimmed)" />
            </Dropzone.Idle>

            <div>
              <Text size="lg" inline fw={600}>
                Tarik dan lepaskan file PDF di sini, atau klik untuk memilih file
              </Text>
              <Text size="sm" c="dimmed" inline mt={7}>
                Format yang didukung: <strong>.pdf</strong> (Maksimum 50MB)
              </Text>
            </div>
          </Group>
        </Dropzone>
      </Paper>

      <Paper p="md" radius="md" withBorder>
        <Title order={4} mb="md">
          Daftar Dokumen Tersimpan ({documents.length})
        </Title>

        {loading && documents.length === 0 ? (
          <Group justify="center" py="xl">
            <Loader size="md" />
            <Text size="sm" c="dimmed">Memuat daftar dokumen...</Text>
          </Group>
        ) : documents.length === 0 ? (
          <Alert color="blue" icon={<IconAlertCircle size={18} />}>
            Belum ada dokumen yang diunggah. Silakan unggah file PDF di atas.
          </Alert>
        ) : (
          <Table highlightOnHover verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Nama File</Table.Th>
                <Table.Th>Mata Pelajaran</Table.Th>
                <Table.Th>Metode Chunking</Table.Th>
                <Table.Th>Status Ingestion</Table.Th>
                <Table.Th>Waktu Upload</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Aksi</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {documents.map((doc) => (
                <Table.Tr key={doc.id}>
                  <Table.Td style={{ fontWeight: 600 }}>{doc.filename}</Table.Td>
                  <Table.Td>
                    <Badge variant="outline" color="blue">{doc.subject}</Badge>
                  </Table.Td>
                  <Table.Td>
                    <Badge
                      variant="light"
                      color={
                        doc.chunking_strategy === 'section_aware'
                          ? 'blue'
                          : doc.chunking_strategy === 'semantic'
                          ? 'violet'
                          : 'cyan'
                      }
                    >
                      {doc.chunking_strategy === 'section_aware'
                        ? 'Section-Aware'
                        : doc.chunking_strategy === 'semantic'
                        ? 'Semantic Chunking'
                        : 'Fixed Chunking'}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{renderStatusBadge(doc.status)}</Table.Td>
                  <Table.Td>{doc.created_at || '-'}</Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>
                    <Group gap="xs" justify="flex-end">
                      <Button
                        size="xs"
                        variant="light"
                        leftSection={<IconEye size={14} />}
                        disabled={doc.status !== 'ready'}
                        onClick={() => handleViewChunks(doc)}
                      >
                        Lihat Chunk
                      </Button>
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        onClick={() => handleDelete(doc.id, doc.filename)}
                        aria-label="Hapus dokumen"
                      >
                        <IconTrash size={18} />
                      </ActionIcon>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Paper>

      {/* Drawer Visualization for Document Chunks */}
      <Drawer
        opened={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={
          <Group gap="xs">
            <IconFileText size={20} color="var(--mantine-color-blue-6)" />
            <Text fw={700} size="lg">
              Visualisasi Chunk: {selectedDocForChunks?.filename}
            </Text>
          </Group>
        }
        position="right"
        size="xl"
      >
        <Stack gap="md">
          {loadingChunks ? (
            <Group justify="center" py="xl">
              <Loader size="md" />
              <Text size="sm" c="dimmed">Memuat daftar chunk dari database...</Text>
            </Group>
          ) : chunks.length === 0 ? (
            <Alert color="yellow" icon={<IconAlertCircle size={18} />}>
              Belum ada chunk yang tersimpan untuk dokumen ini.
            </Alert>
          ) : (
            <>
              {/* Summary Stats Header */}
              <Paper p="sm" radius="md" withBorder bg="var(--mantine-color-body)">
                <Group justify="space-between" align="center">
                  <div>
                    <Text size="xs" c="dimmed">Total Hasil Chunking</Text>
                    <Text fw={700} size="xl" style={{ color: 'var(--mantine-color-blue-6)' }}>
                      {chunks.length} Chunk
                    </Text>
                  </div>
                  <Group gap="xs" wrap="wrap">
                    <Badge color="blue" variant="light">
                      Materi Pokok: {chunks.filter((c) => ['materi_pokok', 'konsep'].includes((c.category || '').toLowerCase())).length}
                    </Badge>
                    <Badge color="teal" variant="light">
                      Uraian: {chunks.filter((c) => ['uraian_materi', 'narasi'].includes((c.category || '').toLowerCase())).length}
                    </Badge>
                    <Badge color="cyan" variant="light">
                      Studi Kasus: {chunks.filter((c) => (c.category || '').toLowerCase() === 'studi_kasus').length}
                    </Badge>
                    <Badge color="orange" variant="light">
                      Aktivitas: {chunks.filter((c) => ['aktivitas_diskusi', 'instruksi'].includes((c.category || '').toLowerCase())).length}
                    </Badge>
                    <Badge color="grape" variant="light">
                      Rangkuman: {chunks.filter((c) => ['rangkuman', 'evaluasi'].includes((c.category || '').toLowerCase())).length}
                    </Badge>
                  </Group>
                </Group>
              </Paper>

              {/* Search Bar */}
              <TextInput
                placeholder="Cari kata kunci dalam chunk..."
                leftSection={<IconSearch size={16} />}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.currentTarget.value)}
              />

              {/* List of Chunks */}
              <ScrollArea style={{ height: 'calc(100vh - 250px)' }}>
                <Stack gap="sm">
                  {filteredChunks.map((chunk, index) => (
                    <Card key={chunk.id} shadow="xs" padding="md" radius="md" withBorder>
                      <Group justify="space-between" mb="xs">
                        <Group gap="xs">
                          <Badge variant="outline" color="gray" size="sm">
                            Chunk #{chunk.chunk_index !== undefined && chunk.chunk_index !== null ? chunk.chunk_index + 1 : index + 1}
                          </Badge>
                          {chunk.page_number && (
                            <Badge variant="filled" color="indigo" size="sm">
                              Hal. {chunk.page_number}
                            </Badge>
                          )}
                          {renderCategoryBadge(chunk.category)}
                        </Group>
                        <Text size="xs" c="dimmed">
                          {chunk.word_count || chunk.text.split(/\s+/).length} Kata ({chunk.text.length} karakter)
                        </Text>
                      </Group>

                      {(chunk.chapter || chunk.section_heading) && (
                        <Group gap="xs" mb="xs">
                          {chunk.chapter && (
                            <Badge color="cyan" variant="dot" size="xs">
                              {chunk.chapter}
                            </Badge>
                          )}
                          {chunk.section_heading && (
                            <Badge color="dark" variant="dot" size="xs">
                              {chunk.section_heading}
                            </Badge>
                          )}
                        </Group>
                      )}

                      <Paper
                        p="xs"
                        px="sm"
                        radius="xs"
                        withBorder
                        style={{
                          backgroundColor: 'rgba(0, 0, 0, 0.02)',
                          fontSize: '13px',
                          whiteSpace: 'pre-wrap',
                          lineHeight: '1.5',
                        }}
                      >
                        {chunk.text}
                      </Paper>
                    </Card>
                  ))}
                </Stack>
              </ScrollArea>
            </>
          )}
        </Stack>
      </Drawer>
    </Stack>
  );
}
