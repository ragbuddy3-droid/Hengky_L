'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { PAGE_TITLE_FZ } from '@/components/common/PageHeader';
import { Alert, Anchor, Button, Checkbox, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core';
import { hasLength, isEmail, matchesField, useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconAlertCircle } from '@tabler/icons-react';
import { ApiError } from '@/lib/api/client';
import { useRegister } from '@/hooks/useAuth';
import { MIN_PASSWORD_LENGTH, PasswordStrength } from './PasswordStrength';
import { safeNext, useRedirectIfLoggedIn } from './useAuthRedirect';
import { validateName } from './validators';

export function RegisterForm({ next }: { next?: string }) {
  const router = useRouter();
  const target = safeNext(next);
  const register = useRegister();
  const [serverError, setServerError] = useState<string | null>(null);
  useRedirectIfLoggedIn(target);

  const form = useForm({
    mode: 'uncontrolled',
    initialValues: { name: '', email: '', password: '', confirmPassword: '', remember: false },
    validate: {
      name: validateName,
      email: isEmail('Masukkan alamat email yang valid.'),
      password: hasLength({ min: MIN_PASSWORD_LENGTH }, `Password minimal ${MIN_PASSWORD_LENGTH} karakter.`),
      confirmPassword: matchesField('password', 'Konfirmasi password tidak sama.'),
    },
  });
  const password = form.useWatchValue('password');

  const handleSubmit = form.onSubmit(({ name, email, password, remember }) => {
    setServerError(null);
    return register
      .mutateAsync({ name: name.trim(), email: email.trim(), password, remember })
      .then((user) => {
        notifications.show({
          color: 'green',
          title: `Halo, ${user.name}!`,
          message: 'Akun berhasil dibuat. Riwayat dari mode tamu sudah dipindahkan ke akun Anda.',
        });
        router.replace(target);
      })
      .catch((err: Error) => {
        if (err instanceof ApiError && err.status === 409) form.setFieldError('email', err.message);
        else setServerError(err.message);
      });
  });

  const loginHref = next ? `/login?next=${encodeURIComponent(target)}` : '/login';

  return (
    <Stack gap="lg">
      <div>
        <Title order={1} fz={PAGE_TITLE_FZ}>
          Buat akun Soalnya
        </Title>
        <Text c="dimmed" mt={6}>
          Simpan dokumen, riwayat chat, dan Bank Soal Anda secara permanen.
        </Text>
      </div>

      {serverError && (
        <Alert color="red" variant="light" icon={<IconAlertCircle size={18} aria-hidden />} role="alert">
          {serverError}
        </Alert>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <Stack gap="md">
          <TextInput
            label="Nama"
            placeholder="Nama lengkap"
            autoComplete="name"
            size="md"
            required
            key={form.key('name')}
            {...form.getInputProps('name')}
          />
          <TextInput
            label="Email"
            placeholder="nama@email.com"
            type="email"
            autoComplete="email"
            inputMode="email"
            size="md"
            required
            key={form.key('email')}
            {...form.getInputProps('email')}
          />
          <PasswordInput
            label="Password"
            placeholder={`Minimal ${MIN_PASSWORD_LENGTH} karakter`}
            autoComplete="new-password"
            size="md"
            required
            key={form.key('password')}
            {...form.getInputProps('password')}
          />
          <PasswordStrength value={password} />
          <PasswordInput
            label="Konfirmasi password"
            placeholder="Ulangi password"
            autoComplete="new-password"
            size="md"
            required
            visibilityToggleButtonProps={{ 'aria-label': 'Tampilkan atau sembunyikan konfirmasi password' }}
            key={form.key('confirmPassword')}
            {...form.getInputProps('confirmPassword')}
          />
          <Checkbox
            label="Ingat saya selama 30 hari"
            key={form.key('remember')}
            {...form.getInputProps('remember', { type: 'checkbox' })}
          />
          <Button type="submit" size="md" fullWidth loading={form.submitting}>
            Daftar
          </Button>
        </Stack>
      </form>

      <Text size="sm" ta="center">
        Sudah punya akun?{' '}
        <Anchor component={Link} href={loginHref} fw={600}>
          Masuk
        </Anchor>
      </Text>
      <Text size="xs" c="dimmed" ta="center">
        Dokumen dan chat dari mode tamu akan otomatis dipindahkan ke akun baru Anda.
      </Text>
    </Stack>
  );
}
