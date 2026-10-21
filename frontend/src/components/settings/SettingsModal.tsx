'use client';

import { useRouter } from 'next/navigation';
import {
  Alert,
  Box,
  Button,
  Group,
  Modal,
  PasswordInput,
  SegmentedControl,
  Stack,
  Tabs,
  Text,
  TextInput,
  Title,
  useMantineColorScheme,
  type MantineColorScheme,
} from '@mantine/core';
import { hasLength, isNotEmpty, matchesField, useForm } from '@mantine/form';
import { useMediaQuery } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { IconAlertTriangle, IconLock, IconPalette, IconUser, IconUserX } from '@tabler/icons-react';
import { MIN_PASSWORD_LENGTH, PasswordStrength } from '@/features/auth/PasswordStrength';
import { validateName } from '@/features/auth/validators';
import { useChangePassword, useDeleteAccount, useMe, useUpdateProfile } from '@/hooks/useAuth';
import { ApiError } from '@/lib/api/client';
import { formatDate } from '@/lib/format';
import { DANGER_COLOR, THEME_OPTIONS } from '@/theme/theme';
import type { User } from '@/types/auth';

const DELETE_PHRASE = 'HAPUS';

function SectionTitle({ title, description }: { title: string; description: string }) {
  return (
    <Box mb="md">
      <Title order={3} fz="lg">
        {title}
      </Title>
      <Text size="sm" c="dimmed" mt={2}>
        {description}
      </Text>
    </Box>
  );
}

function ProfileTab({ user }: { user: User }) {
  const updateProfile = useUpdateProfile();
  const form = useForm({
    mode: 'uncontrolled',
    initialValues: { name: user.name },
    validate: { name: validateName },
  });

  const handleSubmit = form.onSubmit(({ name }) =>
    updateProfile
      .mutateAsync(name.trim())
      .then((updated) => {
        form.setInitialValues({ name: updated.name });
        form.reset();
        notifications.show({ color: 'green', message: 'Profil diperbarui.' });
      })
      .catch((err: Error) => form.setFieldError('name', err.message)),
  );

  return (
    <form onSubmit={handleSubmit} noValidate>
      <SectionTitle title="Profil" description="Nama ini tampil di sidebar dan menu akun." />
      <Stack gap="md">
        <TextInput label="Nama" autoComplete="name" required key={form.key('name')} {...form.getInputProps('name')} />
        <TextInput
          label="Email"
          value={user.email}
          readOnly
          variant="filled"
          description="Email digunakan untuk masuk dan tidak dapat diubah."
        />
        <Text size="xs" c="dimmed">
          Bergabung sejak {formatDate(user.created_at)}
        </Text>
        <Group justify="flex-end">
          <Button type="submit" loading={form.submitting} disabled={!form.isDirty()}>
            Simpan perubahan
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

function SecurityTab() {
  const changePassword = useChangePassword();
  const form = useForm({
    mode: 'uncontrolled',
    initialValues: { current: '', next: '', confirm: '' },
    validate: {
      current: isNotEmpty('Password saat ini wajib diisi.'),
      next: hasLength({ min: MIN_PASSWORD_LENGTH }, `Password minimal ${MIN_PASSWORD_LENGTH} karakter.`),
      confirm: matchesField('next', 'Konfirmasi password tidak sama.'),
    },
  });
  const next = form.useWatchValue('next');

  const handleSubmit = form.onSubmit(({ current, next }) =>
    changePassword
      .mutateAsync({ current_password: current, new_password: next })
      .then(() => {
        form.reset();
        notifications.show({ color: 'green', message: 'Password berhasil diganti.' });
      })
      .catch((err: Error) => {
        if (err instanceof ApiError && err.status >= 400 && err.status < 500) form.setFieldError('current', err.message);
        else notifications.show({ color: 'red', title: 'Gagal mengganti password', message: err.message });
      }),
  );

  return (
    <form onSubmit={handleSubmit} noValidate>
      <SectionTitle title="Keamanan" description="Ganti password secara berkala untuk menjaga akun tetap aman." />
      <Stack gap="md">
        <PasswordInput
          label="Password saat ini"
          autoComplete="current-password"
          required
          key={form.key('current')}
          {...form.getInputProps('current')}
        />
        <PasswordInput
          label="Password baru"
          autoComplete="new-password"
          required
          key={form.key('next')}
          {...form.getInputProps('next')}
        />
        <PasswordStrength value={next} />
        <PasswordInput
          label="Konfirmasi password baru"
          autoComplete="new-password"
          required
          key={form.key('confirm')}
          {...form.getInputProps('confirm')}
        />
        <Group justify="flex-end">
          <Button type="submit" loading={form.submitting}>
            Ganti password
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

function AppearanceTab() {
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  return (
    <div>
      <SectionTitle title="Tampilan" description="Pilih tema terang, gelap, atau ikuti pengaturan perangkat." />
      <Text size="sm" fw={500} mb={6} id="theme-label">
        Tema
      </Text>
      <SegmentedControl
        aria-labelledby="theme-label"
        fullWidth
        value={colorScheme}
        onChange={(value) => setColorScheme(value as MantineColorScheme)}
        data={THEME_OPTIONS.map(({ value, label }) => ({ value, label }))}
      />
    </div>
  );
}

function DeleteAccountTab({ onDeleted }: { onDeleted: () => void }) {
  const deleteAccount = useDeleteAccount();
  const form = useForm({
    mode: 'uncontrolled',
    initialValues: { password: '', phrase: '' },
    validate: {
      password: isNotEmpty('Password wajib diisi.'),
      phrase: (value) => (value.trim() !== DELETE_PHRASE ? `Ketik ${DELETE_PHRASE} untuk melanjutkan.` : null),
    },
  });
  const phrase = form.useWatchValue('phrase');

  const handleSubmit = form.onSubmit(({ password }) =>
    deleteAccount
      .mutateAsync(password)
      .then(() => {
        notifications.show({ color: 'green', message: 'Akun Anda telah dihapus.' });
        onDeleted();
      })
      .catch((err: Error) => {
        if (err instanceof ApiError && err.status >= 400 && err.status < 500) form.setFieldError('password', err.message);
        else notifications.show({ color: 'red', title: 'Gagal menghapus akun', message: err.message });
      }),
  );

  return (
    <form onSubmit={handleSubmit} noValidate>
      <SectionTitle title="Hapus akun" description="Tindakan ini permanen dan tidak dapat dibatalkan." />
      <Stack gap="md">
        <Alert color="red" variant="light" icon={<IconAlertTriangle size={18} aria-hidden />}>
          Semua dokumen, riwayat chat, dan Bank Soal milik akun ini akan dihapus selamanya.
        </Alert>
        <PasswordInput
          label="Password"
          autoComplete="current-password"
          required
          key={form.key('password')}
          {...form.getInputProps('password')}
        />
        <TextInput
          label={
            <>
              Ketik <b>{DELETE_PHRASE}</b> untuk konfirmasi
            </>
          }
          autoComplete="off"
          required
          key={form.key('phrase')}
          {...form.getInputProps('phrase')}
        />
        <Group justify="flex-end">
          <Button
            type="submit"
            color={DANGER_COLOR}
            loading={form.submitting}
            disabled={phrase.trim() !== DELETE_PHRASE}
          >
            Hapus akun permanen
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

export function SettingsModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const router = useRouter();
  const { user } = useMe();
  const isMobile = useMediaQuery('(max-width: 48em)');
  // Tamu hanya punya pengaturan tampilan.
  const defaultTab = user ? 'profil' : 'tampilan';

  const handleDeleted = () => {
    onClose();
    router.push('/chat');
  };

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="Pengaturan"
      size="xl"
      fullScreen={isMobile}
      transitionProps={isMobile ? { transition: 'slide-up', duration: 200 } : undefined}
    >
      <Tabs
        key={defaultTab}
        defaultValue={defaultTab}
        orientation={isMobile ? 'horizontal' : 'vertical'}
        variant={isMobile ? 'default' : 'pills'}
        keepMounted={false}
        styles={
          isMobile
            ? { list: { flexWrap: 'nowrap', overflowX: 'auto' }, tab: { padding: '10px 12px', flexShrink: 0 } }
            : { tab: { justifyContent: 'flex-start' } }
        }
      >
        <Tabs.List mb={isMobile ? 'md' : 0} mr={isMobile ? 0 : 'lg'} miw={isMobile ? undefined : 160} grow={isMobile}>
          {user && (
            <>
              <Tabs.Tab value="profil" leftSection={isMobile ? undefined : <IconUser size={16} aria-hidden />}>
                Profil
              </Tabs.Tab>
              <Tabs.Tab value="keamanan" leftSection={isMobile ? undefined : <IconLock size={16} aria-hidden />}>
                Keamanan
              </Tabs.Tab>
            </>
          )}
          <Tabs.Tab value="tampilan" leftSection={isMobile ? undefined : <IconPalette size={16} aria-hidden />}>
            Tampilan
          </Tabs.Tab>
          {user && (
            <Tabs.Tab value="akun" color="red" leftSection={isMobile ? undefined : <IconUserX size={16} aria-hidden />}>
              Akun
            </Tabs.Tab>
          )}
        </Tabs.List>

        <Box style={{ flex: 1, minWidth: 0 }} pb="xs">
          {user && (
            <>
              <Tabs.Panel value="profil">
                <ProfileTab user={user} />
              </Tabs.Panel>
              <Tabs.Panel value="keamanan">
                <SecurityTab />
              </Tabs.Panel>
            </>
          )}
          <Tabs.Panel value="tampilan">
            <AppearanceTab />
          </Tabs.Panel>
          {user && (
            <Tabs.Panel value="akun">
              <DeleteAccountTab onDeleted={handleDeleted} />
            </Tabs.Panel>
          )}
        </Box>
      </Tabs>
    </Modal>
  );
}
