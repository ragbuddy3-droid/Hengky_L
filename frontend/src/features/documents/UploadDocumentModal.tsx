'use client';

import { ActionIcon, Button, Group, Modal, Paper, Stack, Text, TextInput, ThemeIcon } from '@mantine/core';
import { Dropzone, PDF_MIME_TYPE, type FileRejection } from '@mantine/dropzone';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconFileTypePdf, IconUpload, IconX } from '@tabler/icons-react';
import { useUploadDocument } from '@/hooks/useDocuments';

const MAX_SIZE_MB = 50;

interface UploadFormValues {
  file: File | null;
  subject: string;
}

function formatSize(bytes: number) {
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function UploadDocumentModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const upload = useUploadDocument();
  const form = useForm<UploadFormValues>({
    mode: 'controlled',
    initialValues: { file: null, subject: '' },
    validate: {
      file: (value) => (value ? null : 'Pilih file PDF buku terlebih dahulu.'),
      subject: (value) => (value.trim().length >= 2 ? null : 'Isi mata pelajaran (minimal 2 karakter).'),
    },
  });

  const handleClose = () => {
    if (upload.isPending) return;
    form.reset();
    onClose();
  };

  const handleReject = (rejections: FileRejection[]) => {
    const code = rejections[0]?.errors[0]?.code;
    form.setFieldError(
      'file',
      code === 'file-too-large' ? `Ukuran file melebihi ${MAX_SIZE_MB} MB.` : 'Hanya file PDF yang didukung.',
    );
  };

  const handleSubmit = form.onSubmit(({ file, subject }) => {
    if (!file) return;
    upload.mutate(
      { file, subject: subject.trim() },
      {
        onSuccess: () => {
          notifications.show({
            color: 'teal',
            title: 'Buku diunggah',
            message: `${file.name} sedang diproses. Status akan diperbarui otomatis.`,
          });
          form.reset();
          onClose();
        },
        onError: (err) => notifications.show({ color: 'red', title: 'Gagal mengunggah', message: err.message }),
      },
    );
  });

  const file = form.values.file;

  return (
    <Modal opened={opened} onClose={handleClose} title="Unggah Buku" size="lg">
      <form onSubmit={handleSubmit} noValidate>
        <Stack gap="md">
          {file ? (
            <Paper p="sm" radius="md">
              <Group wrap="nowrap" justify="space-between">
                <Group wrap="nowrap" gap="sm" miw={0}>
                  <ThemeIcon variant="light" color="red" size="lg">
                    <IconFileTypePdf size={20} aria-hidden />
                  </ThemeIcon>
                  <div style={{ minWidth: 0 }}>
                    <Text size="sm" fw={500} truncate>
                      {file.name}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {formatSize(file.size)}
                    </Text>
                  </div>
                </Group>
                <ActionIcon
                  onClick={() => form.setFieldValue('file', null)}
                  aria-label="Hapus file terpilih"
                  disabled={upload.isPending}
                >
                  <IconX size={16} aria-hidden />
                </ActionIcon>
              </Group>
            </Paper>
          ) : (
            <div>
              <Dropzone
                onDrop={(files) => {
                  form.setFieldValue('file', files[0] ?? null);
                  form.clearFieldError('file');
                }}
                onReject={handleReject}
                accept={PDF_MIME_TYPE}
                maxSize={MAX_SIZE_MB * 1024 ** 2}
                maxFiles={1}
                multiple={false}
                radius="md"
              >
                <Stack align="center" gap={6} mih={160} justify="center" style={{ pointerEvents: 'none' }}>
                  <Dropzone.Accept>
                    <IconUpload size={40} color="var(--mantine-color-teal-6)" aria-hidden />
                  </Dropzone.Accept>
                  <Dropzone.Reject>
                    <IconX size={40} color="var(--mantine-color-red-6)" aria-hidden />
                  </Dropzone.Reject>
                  <Dropzone.Idle>
                    <IconFileTypePdf size={40} color="var(--mantine-color-dimmed)" aria-hidden />
                  </Dropzone.Idle>
                  <Text fw={500}>Seret file PDF ke sini atau klik untuk memilih</Text>
                  <Text size="sm" c="dimmed">
                    Satu file PDF, maksimal {MAX_SIZE_MB} MB
                  </Text>
                </Stack>
              </Dropzone>
              {form.errors.file && (
                <Text size="xs" c="var(--app-danger-text)" mt={6} role="alert">
                  {form.errors.file}
                </Text>
              )}
            </div>
          )}

          <TextInput
            label="Mata pelajaran"
            description="Dipakai sebagai konteks saat membuat soal."
            placeholder="contoh: Biologi Kelas X"
            withAsterisk
            disabled={upload.isPending}
            key={form.key('subject')}
            {...form.getInputProps('subject')}
          />

          <Group justify="flex-end" mt="xs">
            <Button variant="default" onClick={handleClose} disabled={upload.isPending}>
              Batal
            </Button>
            <Button type="submit" loading={upload.isPending} leftSection={<IconUpload size={16} aria-hidden />}>
              Unggah
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
